"""Persistent RAG pipeline backed by ChromaDB.

Each user gets an isolated ChromaDB collection. Documents are chunked,
embedded with all-MiniLM-L6-v2, and stored on disk for reuse across requests.
"""

import logging
import uuid

import chromadb

logger = logging.getLogger(__name__)

_client: chromadb.ClientAPI | None = None

_CHUNK_SIZE = 400
_CHUNK_OVERLAP = 60


def _get_client() -> chromadb.ClientAPI:
    """Lazy-init a persistent ChromaDB client (singleton)."""
    global _client  # noqa: PLW0603
    if _client is None:
        from app.core.config import settings  # noqa: PLC0415

        _client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        logger.info("ChromaDB client initialised at %s", settings.CHROMA_PERSIST_DIR)
    return _client


def _get_collection(user_id: uuid.UUID) -> chromadb.Collection:
    """Return (or create) the ChromaDB collection for a user."""
    name = f"user_{str(user_id).replace('-', '')}"
    return _get_client().get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


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
    """Chunk, embed, and upsert a document into ChromaDB.

    Returns the number of chunks indexed. Replaces existing chunks for
    the same source_id (idempotent).
    """
    if not text or not text.strip():
        return 0

    collection = _get_collection(user_id)
    model = _get_model()
    chunks = _chunk_text(text)

    if not chunks:
        return 0

    # Remove any existing chunks for this source_id before upserting
    sid = str(source_id)
    _delete_by_source(collection, sid)

    ids = [f"{sid}_{i}" for i in range(len(chunks))]
    embeddings = model.encode(chunks, show_progress_bar=False).tolist()
    metadatas = [
        {"source_type": source_type, "source_id": sid, "chunk_index": i} for i in range(len(chunks))
    ]

    collection.upsert(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)
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
    """Semantic search across a user's embeddings.

    Returns a list of dicts: {chunk_text, source_type, source_id, distance, chunk_index}.
    """
    collection = _get_collection(user_id)

    if collection.count() == 0:
        return []

    model = _get_model()
    query_embedding = model.encode([query], show_progress_bar=False).tolist()

    where_filter = None
    if source_types:
        if len(source_types) == 1:
            where_filter = {"source_type": source_types[0]}
        else:
            where_filter = {"source_type": {"$in": source_types}}

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=min(top_k, collection.count()),
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    items = []
    for i in range(len(results["ids"][0])):
        items.append(
            {
                "chunk_text": results["documents"][0][i],
                "source_type": results["metadatas"][0][i]["source_type"],
                "source_id": results["metadatas"][0][i]["source_id"],
                "chunk_index": results["metadatas"][0][i]["chunk_index"],
                "distance": results["distances"][0][i],
            }
        )
    return items


def delete_embeddings(user_id: uuid.UUID, source_id: uuid.UUID) -> int:
    """Remove all chunks for a specific document. Returns count deleted."""
    collection = _get_collection(user_id)
    return _delete_by_source(collection, str(source_id))


def _delete_by_source(collection: chromadb.Collection, source_id: str) -> int:
    """Delete all chunks matching a source_id from a collection."""
    existing = collection.get(where={"source_id": source_id}, include=[])
    count = len(existing["ids"])
    if count > 0:
        collection.delete(ids=existing["ids"])
    return count


def get_embedding_stats(user_id: uuid.UUID) -> dict:
    """Return chunk counts grouped by source_type."""
    collection = _get_collection(user_id)
    total = collection.count()
    if total == 0:
        return {"total_chunks": 0, "chunks_by_type": {}}

    all_meta = collection.get(include=["metadatas"])
    counts: dict[str, int] = {}
    for meta in all_meta["metadatas"]:
        st = meta.get("source_type", "unknown")
        counts[st] = counts.get(st, 0) + 1

    return {"total_chunks": total, "chunks_by_type": counts}


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


def reset_client() -> None:
    """Reset the module-level client (for testing)."""
    global _client  # noqa: PLW0603
    _client = None
