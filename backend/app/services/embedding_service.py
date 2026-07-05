"""Pluggable RAG vector store.

Documents are chunked and embedded with all-MiniLM-L6-v2, then persisted through a
backend chosen by ``settings.VECTOR_BACKEND``: ChromaDB (one collection per user) or
Qdrant (a single collection where every point is filtered by ``user_id``).
"""

import abc
import logging
import uuid

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 400
_CHUNK_OVERLAP = 60
_VECTOR_SIZE = 384  # all-MiniLM-L6-v2 embedding dimension
# Stable namespace so re-embedding the same chunk maps to the same Qdrant point id.
_POINT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "ai-career-hub/vector-store")

_store: "VectorStore | None" = None


class VectorStore(abc.ABC):
    """Backend-agnostic interface for the RAG vector store."""

    # Backend id health probes report — the store that was actually built,
    # which is not necessarily what VECTOR_BACKEND says (the "quadrant" lesson).
    name: str

    @abc.abstractmethod
    def upsert(
        self,
        user_id: uuid.UUID,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        """Insert or replace the chunk vectors for a document."""

    @abc.abstractmethod
    def query(
        self,
        user_id: uuid.UUID,
        query_embedding: list[float],
        top_k: int,
        source_types: list[str] | None = None,
    ) -> list[dict]:
        """Return a user's nearest chunks as ranked result dicts."""

    @abc.abstractmethod
    def delete_by_source(self, user_id: uuid.UUID, source_id: uuid.UUID) -> int:
        """Delete every chunk for a source; return how many were removed."""

    @abc.abstractmethod
    def count(self, user_id: uuid.UUID) -> int:
        """Return the total chunk count for a user."""

    @abc.abstractmethod
    def stats(self, user_id: uuid.UUID) -> dict:
        """Return chunk totals grouped by source_type for a user."""

    @abc.abstractmethod
    def healthcheck(self) -> dict:
        """Return {status, detail} for the backend without raising."""


class ChromaVectorStore(VectorStore):
    """ChromaDB backend: an isolated, persistent collection per user."""

    name = "chroma"

    def __init__(self, client=None):
        self._client = client

    def _get_client(self):
        """Lazy-init a persistent ChromaDB client (kept off the import path)."""
        if self._client is None:
            import chromadb  # noqa: PLC0415

            from app.core.config import settings  # noqa: PLC0415

            self._client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
            logger.info("ChromaDB client initialised at %s", settings.CHROMA_PERSIST_DIR)
        return self._client

    def _collection(self, user_id: uuid.UUID):
        """Return (or create) the cosine collection for a user."""
        name = f"user_{str(user_id).replace('-', '')}"
        return self._get_client().get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, user_id, ids, embeddings, documents, metadatas):
        self._collection(user_id).upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def query(self, user_id, query_embedding, top_k, source_types=None):
        collection = self._collection(user_id)
        count = collection.count()
        if count == 0:
            return []

        where_filter = None
        if source_types:
            if len(source_types) == 1:
                where_filter = {"source_type": source_types[0]}
            else:
                where_filter = {"source_type": {"$in": source_types}}

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, count),
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        items = []
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            items.append(
                {
                    "chunk_text": results["documents"][0][i],
                    "source_type": meta["source_type"],
                    "source_id": meta["source_id"],
                    "chunk_index": meta["chunk_index"],
                    "distance": results["distances"][0][i],
                }
            )
        return items

    def delete_by_source(self, user_id, source_id):
        collection = self._collection(user_id)
        existing = collection.get(where={"source_id": str(source_id)}, include=[])
        ids = existing["ids"]
        if ids:
            collection.delete(ids=ids)
        return len(ids)

    def count(self, user_id):
        return self._collection(user_id).count()

    def stats(self, user_id):
        collection = self._collection(user_id)
        total = collection.count()
        if total == 0:
            return {"total_chunks": 0, "chunks_by_type": {}}

        all_meta = collection.get(include=["metadatas"])
        counts: dict[str, int] = {}
        for meta in all_meta["metadatas"]:
            st = meta.get("source_type", "unknown")
            counts[st] = counts.get(st, 0) + 1
        return {"total_chunks": total, "chunks_by_type": counts}

    def healthcheck(self):
        try:
            self._get_client().heartbeat()
            return {"status": "ok", "detail": None}
        except Exception as exc:
            return {"status": "down", "detail": str(exc)}


class QdrantVectorStore(VectorStore):
    """Qdrant backend: one shared collection, isolated by a mandatory user_id filter."""

    name = "qdrant"

    def __init__(self, client=None, collection: str | None = None):
        self._client = client
        self._collection_name = collection
        self._ensured = False

    def _get_client(self):
        """Lazy-init the Qdrant Cloud client (kept off the import path)."""
        if self._client is None:
            from qdrant_client import QdrantClient  # noqa: PLC0415

            from app.core.config import settings  # noqa: PLC0415

            self._client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
            logger.info("Qdrant client initialised")
        return self._client

    def _name(self) -> str:
        """Resolve the collection name, defaulting to the configured one."""
        if self._collection_name is None:
            from app.core.config import settings  # noqa: PLC0415

            self._collection_name = settings.QDRANT_COLLECTION
        return self._collection_name

    @staticmethod
    def _models():
        """Return the qdrant_client model namespace (Filter, PointStruct, ...)."""
        from qdrant_client import models  # noqa: PLC0415

        return models

    def _ensure_collection(self) -> None:
        """Create the collection on first use; safe under concurrent creation."""
        if self._ensured:
            return
        client = self._get_client()
        name = self._name()
        if not client.collection_exists(name):
            m = self._models()
            try:
                client.create_collection(
                    collection_name=name,
                    vectors_config=m.VectorParams(size=_VECTOR_SIZE, distance=m.Distance.COSINE),
                )
            except Exception:
                # Lost the create race with another worker — fine as long as it now exists.
                if not client.collection_exists(name):
                    raise
        self._ensured = True

    def _point_id(self, user_id, source_id, chunk_index: int) -> str:
        """Deterministic point id so re-embedding replaces the same chunk."""
        return str(uuid.uuid5(_POINT_NAMESPACE, f"{user_id}:{source_id}:{chunk_index}"))

    def _user_filter(self, user_id, source_types: list[str] | None = None):
        """Build the mandatory user_id filter, optionally narrowed by source_type."""
        m = self._models()
        must = [m.FieldCondition(key="user_id", match=m.MatchValue(value=str(user_id)))]
        if source_types:
            must.append(
                m.FieldCondition(key="source_type", match=m.MatchAny(any=list(source_types)))
            )
        return m.Filter(must=must)

    def upsert(self, user_id, ids, embeddings, documents, metadatas):
        self._ensure_collection()
        m = self._models()
        points = [
            m.PointStruct(
                id=self._point_id(user_id, meta["source_id"], meta["chunk_index"]),
                vector=embedding,
                payload={
                    "user_id": str(user_id),
                    "source_type": meta["source_type"],
                    "source_id": meta["source_id"],
                    "chunk_index": meta["chunk_index"],
                    "text": document,
                },
            )
            for embedding, document, meta in zip(embeddings, documents, metadatas, strict=True)
        ]
        self._get_client().upsert(collection_name=self._name(), points=points)

    def query(self, user_id, query_embedding, top_k, source_types=None):
        self._ensure_collection()
        response = self._get_client().query_points(
            collection_name=self._name(),
            query=query_embedding,
            limit=top_k,
            query_filter=self._user_filter(user_id, source_types),
            with_payload=True,
        )

        items = []
        for point in response.points:
            payload = point.payload or {}
            items.append(
                {
                    "chunk_text": payload.get("text", ""),
                    "source_type": payload.get("source_type"),
                    "source_id": payload.get("source_id"),
                    "chunk_index": payload.get("chunk_index"),
                    # Chroma reports cosine distance; Qdrant reports similarity. Convert so
                    # callers keep the "lower is closer" contract with ordering preserved.
                    "distance": 1.0 - point.score,
                }
            )
        return items

    def delete_by_source(self, user_id, source_id):
        self._ensure_collection()
        m = self._models()
        flt = m.Filter(
            must=[
                m.FieldCondition(key="user_id", match=m.MatchValue(value=str(user_id))),
                m.FieldCondition(key="source_id", match=m.MatchValue(value=str(source_id))),
            ]
        )
        client = self._get_client()
        name = self._name()
        # Qdrant's delete does not report a count, so tally the match beforehand.
        removed = client.count(collection_name=name, count_filter=flt, exact=True).count
        if removed:
            client.delete(collection_name=name, points_selector=m.FilterSelector(filter=flt))
        return removed

    def count(self, user_id):
        self._ensure_collection()
        result = self._get_client().count(
            collection_name=self._name(),
            count_filter=self._user_filter(user_id),
            exact=True,
        )
        return result.count

    def stats(self, user_id):
        self._ensure_collection()
        client = self._get_client()
        name = self._name()
        flt = self._user_filter(user_id)

        counts: dict[str, int] = {}
        total = 0
        offset = None
        while True:
            records, offset = client.scroll(
                collection_name=name,
                scroll_filter=flt,
                with_payload=["source_type"],
                with_vectors=False,
                limit=256,
                offset=offset,
            )
            for record in records:
                st = (record.payload or {}).get("source_type", "unknown")
                counts[st] = counts.get(st, 0) + 1
                total += 1
            if offset is None:
                break
        return {"total_chunks": total, "chunks_by_type": counts}

    def healthcheck(self):
        try:
            self._get_client().get_collections()
            return {"status": "ok", "detail": None}
        except Exception as exc:
            return {"status": "down", "detail": str(exc)}


def _get_store() -> VectorStore:
    """Return the configured vector store singleton."""
    global _store  # noqa: PLW0603
    if _store is None:
        from app.core.config import settings  # noqa: PLC0415

        if settings.VECTOR_BACKEND == "qdrant":
            _store = QdrantVectorStore()
        else:
            _store = ChromaVectorStore()
    return _store


def _get_model():
    """Reuse the sentence-transformers model singleton from ats_scorer."""
    from app.services.ats_scorer import _get_model as _ats_get_model  # noqa: PLC0415

    return _ats_get_model()


def _chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: PLC0415

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_CHUNK_SIZE,
        chunk_overlap=_CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    return splitter.split_text(text)


def embed_document(
    user_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
    text: str,
) -> int:
    """Chunk, embed, and upsert a document into the vector store.

    Returns the number of chunks indexed. Replaces existing chunks for
    the same source_id (idempotent).
    """
    if not text or not text.strip():
        return 0

    chunks = _chunk_text(text)
    if not chunks:
        return 0

    store = _get_store()
    # Remove any existing chunks for this source_id before upserting.
    store.delete_by_source(user_id, source_id)

    model = _get_model()
    embeddings = model.encode(chunks, show_progress_bar=False).tolist()

    sid = str(source_id)
    ids = [f"{sid}_{i}" for i in range(len(chunks))]
    metadatas = [
        {"source_type": source_type, "source_id": sid, "chunk_index": i} for i in range(len(chunks))
    ]

    store.upsert(user_id, ids, embeddings, chunks, metadatas)
    logger.info(
        "Embedded %d chunks for %s/%s (user=%s)",
        len(chunks),
        source_type,
        sid[:8],
        str(user_id)[:8],
    )
    return len(chunks)


def retrieve_context(
    user_id: uuid.UUID,
    query: str,
    top_k: int = 6,
    source_types: list[str] | None = None,
) -> list[dict]:
    """Semantic search across a user's embeddings, nearest first.

    Returns a list of dicts: {chunk_text, source_type, source_id, chunk_index, distance}.
    """
    model = _get_model()
    query_embedding = model.encode([query], show_progress_bar=False)[0].tolist()
    return _get_store().query(user_id, query_embedding, top_k, source_types)


def delete_embeddings(user_id: uuid.UUID, source_id: uuid.UUID) -> int:
    """Remove all chunks for a specific document. Returns count deleted."""
    return _get_store().delete_by_source(user_id, source_id)


def get_embedding_stats(user_id: uuid.UUID) -> dict:
    """Return chunk counts grouped by source_type."""
    return _get_store().stats(user_id)


def reindex_all_documents(user_id: uuid.UUID, documents: list[dict]) -> dict:
    """Re-embed all documents for a user. Each dict has {source_type, source_id, text}.

    Returns {total_chunks, documents_processed}.
    """
    total_chunks = 0
    for doc in documents:
        chunks = embed_document(
            user_id=user_id,
            source_type=doc["source_type"],
            source_id=uuid.UUID(doc["source_id"])
            if isinstance(doc["source_id"], str)
            else doc["source_id"],
            text=doc["text"],
        )
        total_chunks += chunks

    return {"total_chunks": total_chunks, "documents_processed": len(documents)}


def vector_healthcheck() -> dict:
    """Cheap liveness probe for the active vector backend; never raises."""
    try:
        store = _get_store()
        result = store.healthcheck()
    except Exception as exc:
        from app.core.config import settings  # noqa: PLC0415

        return {"backend": settings.VECTOR_BACKEND, "status": "down", "detail": str(exc)}
    # Name the store the factory built, not the configured string — the two
    # diverged once ("quadrant") and the probe reported the typo as healthy.
    return {"backend": store.name, "status": result["status"], "detail": result.get("detail")}


def reset_client() -> None:
    """Reset the module-level vector store (for testing)."""
    global _store  # noqa: PLW0603
    _store = None
