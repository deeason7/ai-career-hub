"""Tests for the pluggable embedding service across vector backends."""

import uuid
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

_EMBEDDING_DIM = 384

_SAMPLE_RESUME = (
    "John Doe — Software Engineer\n\n"
    "Experience:\n"
    "Senior Developer at Acme Corp (2020-2024). "
    "Built microservices with Python, FastAPI, and PostgreSQL. "
    "Led a team of 5 engineers. Deployed to AWS using Docker and Kubernetes.\n\n"
    "Education:\n"
    "B.S. Computer Science, MIT, 2020.\n\n"
    "Skills:\n"
    "Python, FastAPI, Docker, Kubernetes, PostgreSQL, Redis, AWS, CI/CD, "
    "machine learning, NLP, LangChain, React, TypeScript."
)

_SAMPLE_JD = (
    "We are looking for a Senior Software Engineer with experience in "
    "Python, FastAPI, and cloud infrastructure (AWS). "
    "The ideal candidate has built production microservices and has "
    "experience with Docker, CI/CD, and database systems."
)


def _mock_model():
    """Return a fake sentence-transformers model with deterministic 384-dim vectors."""
    model = MagicMock()

    def _encode(texts, **kwargs):
        return np.random.default_rng(42).random((len(texts), _EMBEDDING_DIM)).astype(np.float32)

    model.encode = _encode
    return model


def _chroma_store():
    """Build a ChromaVectorStore backed by an in-memory client."""
    import chromadb

    from app.services.embedding_service import ChromaVectorStore

    return ChromaVectorStore(client=chromadb.EphemeralClient())


def _qdrant_store():
    """Build a QdrantVectorStore backed by an in-memory client (no network)."""
    from qdrant_client import QdrantClient

    from app.services.embedding_service import QdrantVectorStore

    return QdrantVectorStore(client=QdrantClient(location=":memory:"), collection="test_vectors")


# --- Fixtures ---


@pytest.fixture(autouse=True)
def _isolate():
    """Mock the shared embedding model and reset the store singleton per test."""
    from app.services import embedding_service

    with patch("app.services.ats_scorer._get_model", return_value=_mock_model()):
        embedding_service.reset_client()
        yield
        embedding_service.reset_client()


@pytest.fixture(params=["chroma", "qdrant"])
def store(request):
    """A live store for each backend, exercised through identical assertions."""
    if request.param == "chroma":
        return _chroma_store()
    return _qdrant_store()


@pytest.fixture()
def inject_store(store):
    """Wire the parametrized store into the module so public functions use it."""
    from app.services import embedding_service

    embedding_service._store = store
    return store


@pytest.fixture()
def user_id():
    return uuid.uuid4()


@pytest.fixture()
def source_id():
    return uuid.uuid4()


# --- Public API parity across both backends ---


class TestBackendParity:
    def test_embed_retrieve_delete_count_stats(self, inject_store, user_id, source_id):
        from app.services import embedding_service as es

        n = es.embed_document(user_id, "resume", source_id, _SAMPLE_RESUME)
        assert n > 0
        assert inject_store.count(user_id) == n
        stats = es.get_embedding_stats(user_id)
        assert stats == {"total_chunks": n, "chunks_by_type": {"resume": n}}

        results = es.retrieve_context(user_id, _SAMPLE_JD, top_k=3)
        assert 0 < len(results) <= 3
        distances = [r["distance"] for r in results]
        assert distances == sorted(distances)  # closest-first ordering is preserved
        for r in results:
            assert set(r) == {"chunk_text", "source_type", "source_id", "chunk_index", "distance"}
            assert r["source_type"] == "resume"
            assert isinstance(r["distance"], float)

        deleted = es.delete_embeddings(user_id, source_id)
        assert deleted == n
        assert inject_store.count(user_id) == 0
        assert es.get_embedding_stats(user_id) == {"total_chunks": 0, "chunks_by_type": {}}
        assert es.retrieve_context(user_id, _SAMPLE_JD) == []

    def test_user_isolation(self, inject_store, source_id):
        from app.services import embedding_service as es

        owner, other = uuid.uuid4(), uuid.uuid4()
        es.embed_document(owner, "resume", source_id, _SAMPLE_RESUME)

        assert es.get_embedding_stats(owner)["total_chunks"] > 0
        assert es.get_embedding_stats(other)["total_chunks"] == 0
        assert inject_store.count(other) == 0
        assert es.retrieve_context(other, _SAMPLE_JD) == []

    def test_reembedding_is_idempotent(self, inject_store, user_id, source_id):
        from app.services import embedding_service as es

        es.embed_document(user_id, "resume", source_id, _SAMPLE_RESUME)
        first = es.get_embedding_stats(user_id)["total_chunks"]
        es.embed_document(user_id, "resume", source_id, _SAMPLE_RESUME)
        second = es.get_embedding_stats(user_id)["total_chunks"]

        assert first > 0
        assert first == second

    def test_source_type_filter(self, inject_store, user_id):
        from app.services import embedding_service as es

        es.embed_document(user_id, "resume", uuid.uuid4(), _SAMPLE_RESUME)
        es.embed_document(user_id, "cover_letter", uuid.uuid4(), "Dear Hiring Manager, thank you.")

        resume_only = es.retrieve_context(user_id, _SAMPLE_JD, source_types=["resume"])
        assert resume_only
        assert all(r["source_type"] == "resume" for r in resume_only)

    def test_empty_text_returns_zero(self, inject_store, user_id, source_id):
        from app.services import embedding_service as es

        assert es.embed_document(user_id, "resume", source_id, "") == 0
        assert es.embed_document(user_id, "resume", source_id, "   ") == 0
        assert inject_store.count(user_id) == 0

    def test_empty_collection_returns_empty(self, inject_store, user_id):
        from app.services import embedding_service as es

        assert es.retrieve_context(user_id, _SAMPLE_JD) == []

    def test_reindex_processes_all_docs(self, inject_store, user_id):
        from app.services import embedding_service as es

        docs = [
            {"source_type": "resume", "source_id": str(uuid.uuid4()), "text": _SAMPLE_RESUME},
            {"source_type": "job_description", "source_id": str(uuid.uuid4()), "text": _SAMPLE_JD},
        ]
        result = es.reindex_all_documents(user_id, docs)
        assert result["documents_processed"] == 2
        assert result["total_chunks"] > 0
        assert es.get_embedding_stats(user_id)["total_chunks"] == result["total_chunks"]


# --- Store interface exercised directly (backend-explicit) ---


class TestStoreInterfaceDirect:
    def test_upsert_query_count_delete_stats(self, store, user_id, source_id):
        model = _mock_model()
        chunks = ["alpha experience python", "beta education degree", "gamma skills docker"]
        embeddings = model.encode(chunks).tolist()
        sid = str(source_id)
        ids = [f"{sid}_{i}" for i in range(len(chunks))]
        metadatas = [
            {"source_type": "resume", "source_id": sid, "chunk_index": i}
            for i in range(len(chunks))
        ]

        store.upsert(user_id, ids, embeddings, chunks, metadatas)
        assert store.count(user_id) == 3

        query = model.encode(["python developer"]).tolist()[0]
        results = store.query(user_id, query, top_k=2)
        assert len(results) == 2
        assert all(r["source_type"] == "resume" for r in results)

        assert store.stats(user_id) == {"total_chunks": 3, "chunks_by_type": {"resume": 3}}

        assert store.delete_by_source(user_id, source_id) == 3
        assert store.count(user_id) == 0
        assert store.stats(user_id) == {"total_chunks": 0, "chunks_by_type": {}}


# --- Backend selection (config-gated factory) ---


class TestBackendFactory:
    def test_defaults_to_chroma(self, monkeypatch):
        from app.core.config import settings
        from app.services import embedding_service as es

        monkeypatch.setattr(settings, "VECTOR_BACKEND", "chroma")
        es.reset_client()
        assert isinstance(es._get_store(), es.ChromaVectorStore)

    def test_selects_qdrant_when_configured(self, monkeypatch):
        from app.core.config import settings
        from app.services import embedding_service as es

        monkeypatch.setattr(settings, "VECTOR_BACKEND", "qdrant")
        es.reset_client()
        assert isinstance(es._get_store(), es.QdrantVectorStore)

    def test_store_is_a_singleton(self, monkeypatch):
        from app.core.config import settings
        from app.services import embedding_service as es

        monkeypatch.setattr(settings, "VECTOR_BACKEND", "chroma")
        es.reset_client()
        assert es._get_store() is es._get_store()

    def test_rejects_unknown_backend_at_validation(self):
        from pydantic import ValidationError

        from app.core.config import Settings

        with pytest.raises(ValidationError):
            Settings(VECTOR_BACKEND="quadrant")

    def test_accepts_the_two_known_backends(self):
        from app.core.config import Settings

        assert Settings(VECTOR_BACKEND="chroma").VECTOR_BACKEND == "chroma"
        assert Settings(VECTOR_BACKEND="qdrant").VECTOR_BACKEND == "qdrant"


# --- Health checks ---


class TestHealthcheck:
    def test_store_healthcheck_ok(self, store):
        assert store.healthcheck() == {"status": "ok", "detail": None}

    def test_store_healthcheck_reports_down_without_raising(self):
        from app.services.embedding_service import QdrantVectorStore

        bad = MagicMock()
        bad.get_collections.side_effect = RuntimeError("cluster unreachable")
        result = QdrantVectorStore(client=bad, collection="x").healthcheck()

        assert result["status"] == "down"
        assert "cluster unreachable" in result["detail"]

    def test_vector_healthcheck_reports_active_backend(self, monkeypatch):
        from app.core.config import settings
        from app.services import embedding_service as es

        monkeypatch.setattr(settings, "VECTOR_BACKEND", "chroma")
        es._store = _chroma_store()
        assert es.vector_healthcheck() == {"backend": "chroma", "status": "ok", "detail": None}

    def test_vector_healthcheck_never_raises_when_down(self, monkeypatch):
        from app.core.config import settings
        from app.services import embedding_service as es
        from app.services.embedding_service import QdrantVectorStore

        monkeypatch.setattr(settings, "VECTOR_BACKEND", "qdrant")
        bad = MagicMock()
        bad.get_collections.side_effect = RuntimeError("boom")
        es._store = QdrantVectorStore(client=bad, collection="x")

        assert es.vector_healthcheck() == {"backend": "qdrant", "status": "down", "detail": "boom"}

    def test_vector_healthcheck_names_the_resolved_store(self, monkeypatch):
        """If config and factory ever diverge again, the probe must expose it."""
        from app.core.config import settings
        from app.services import embedding_service as es

        monkeypatch.setattr(settings, "VECTOR_BACKEND", "chroma")
        es._store = _qdrant_store()
        assert es.vector_healthcheck()["backend"] == "qdrant"


# --- cover_letter _chroma_retrieve fallback ---


class TestChromaRetrieveFallback:
    def test_returns_none_when_empty(self, user_id):
        from app.services import embedding_service as es
        from app.services.cover_letter import _chroma_retrieve

        es._store = _chroma_store()
        assert _chroma_retrieve(user_id, _SAMPLE_JD) is None

    def test_returns_context_when_data_exists(self, user_id, source_id):
        from app.services import embedding_service as es
        from app.services.cover_letter import _chroma_retrieve

        es._store = _chroma_store()
        es.embed_document(user_id, "resume", source_id, _SAMPLE_RESUME)

        result = _chroma_retrieve(user_id, _SAMPLE_JD)
        assert result is not None
        context, chunks_used = result
        assert isinstance(context, str)
        assert chunks_used > 0
