"""Tests for the ChromaDB embedding service and RAG endpoints."""

import uuid
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# --- Fixtures ---


@pytest.fixture(autouse=True)
def _isolate_chroma(tmp_path):
    """Use an in-memory ChromaDB client for every test."""
    import chromadb

    from app.services import embedding_service

    test_client = chromadb.EphemeralClient()
    embedding_service._client = test_client
    yield
    embedding_service._client = None


@pytest.fixture()
def user_id():
    return uuid.uuid4()


@pytest.fixture()
def source_id():
    return uuid.uuid4()


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

_EMBEDDING_DIM = 384


def _mock_model():
    """Return a mock sentence-transformers model."""
    model = MagicMock()

    def _encode(texts, **kwargs):
        return np.random.default_rng(42).random((len(texts), _EMBEDDING_DIM)).astype(np.float32)

    model.encode = _encode
    return model


# --- embed_document ---


class TestEmbedDocument:
    @patch("app.services.embedding_service._get_model", return_value=_mock_model())
    def test_creates_chunks(self, _mock, user_id, source_id):
        from app.services.embedding_service import embed_document

        count = embed_document(user_id, "resume", source_id, _SAMPLE_RESUME)
        assert count > 0

    @patch("app.services.embedding_service._get_model", return_value=_mock_model())
    def test_idempotent(self, _mock, user_id, source_id):
        from app.services.embedding_service import embed_document, get_embedding_stats

        embed_document(user_id, "resume", source_id, _SAMPLE_RESUME)
        first_stats = get_embedding_stats(user_id)

        embed_document(user_id, "resume", source_id, _SAMPLE_RESUME)
        second_stats = get_embedding_stats(user_id)

        assert first_stats["total_chunks"] == second_stats["total_chunks"]

    @patch("app.services.embedding_service._get_model", return_value=_mock_model())
    def test_empty_text_returns_zero(self, _mock, user_id, source_id):
        from app.services.embedding_service import embed_document

        assert embed_document(user_id, "resume", source_id, "") == 0
        assert embed_document(user_id, "resume", source_id, "   ") == 0


# --- retrieve_context ---


class TestRetrieveContext:
    @patch("app.services.embedding_service._get_model", return_value=_mock_model())
    def test_returns_ranked_results(self, _mock, user_id, source_id):
        from app.services.embedding_service import embed_document, retrieve_context

        embed_document(user_id, "resume", source_id, _SAMPLE_RESUME)
        results = retrieve_context(user_id, _SAMPLE_JD, top_k=3)

        assert len(results) > 0
        assert len(results) <= 3
        for r in results:
            assert "chunk_text" in r
            assert "source_type" in r
            assert "distance" in r

    @patch("app.services.embedding_service._get_model", return_value=_mock_model())
    def test_filters_by_source_type(self, _mock, user_id, source_id):
        from app.services.embedding_service import embed_document, retrieve_context

        embed_document(user_id, "resume", source_id, _SAMPLE_RESUME)
        cl_id = uuid.uuid4()
        embed_document(user_id, "cover_letter", cl_id, "Dear Hiring Manager...")

        resume_only = retrieve_context(user_id, _SAMPLE_JD, source_types=["resume"])
        for r in resume_only:
            assert r["source_type"] == "resume"

    @patch("app.services.embedding_service._get_model", return_value=_mock_model())
    def test_empty_collection_returns_empty(self, _mock, user_id):
        from app.services.embedding_service import retrieve_context

        results = retrieve_context(user_id, _SAMPLE_JD)
        assert results == []


# --- delete_embeddings ---


class TestDeleteEmbeddings:
    @patch("app.services.embedding_service._get_model", return_value=_mock_model())
    def test_removes_all_chunks(self, _mock, user_id, source_id):
        from app.services.embedding_service import (
            delete_embeddings,
            embed_document,
            get_embedding_stats,
        )

        embed_document(user_id, "resume", source_id, _SAMPLE_RESUME)
        assert get_embedding_stats(user_id)["total_chunks"] > 0

        deleted = delete_embeddings(user_id, source_id)
        assert deleted > 0
        assert get_embedding_stats(user_id)["total_chunks"] == 0


# --- get_embedding_stats ---


class TestGetEmbeddingStats:
    @patch("app.services.embedding_service._get_model", return_value=_mock_model())
    def test_counts_by_type(self, _mock, user_id, source_id):
        from app.services.embedding_service import embed_document, get_embedding_stats

        embed_document(user_id, "resume", source_id, _SAMPLE_RESUME)
        cl_id = uuid.uuid4()
        embed_document(user_id, "cover_letter", cl_id, "Dear Hiring Manager, I am writing...")

        stats = get_embedding_stats(user_id)
        assert stats["total_chunks"] > 0
        assert "resume" in stats["chunks_by_type"]
        assert "cover_letter" in stats["chunks_by_type"]

    def test_empty_user(self, user_id):
        from app.services.embedding_service import get_embedding_stats

        stats = get_embedding_stats(user_id)
        assert stats == {"total_chunks": 0, "chunks_by_type": {}}


# --- reindex_all_documents ---


class TestReindex:
    @patch("app.services.embedding_service._get_model", return_value=_mock_model())
    def test_reindex_processes_all_docs(self, _mock, user_id):
        from app.services.embedding_service import get_embedding_stats, reindex_all_documents

        docs = [
            {"source_type": "resume", "source_id": str(uuid.uuid4()), "text": _SAMPLE_RESUME},
            {"source_type": "job_description", "source_id": str(uuid.uuid4()), "text": _SAMPLE_JD},
        ]
        result = reindex_all_documents(user_id, docs)
        assert result["documents_processed"] == 2
        assert result["total_chunks"] > 0

        stats = get_embedding_stats(user_id)
        assert stats["total_chunks"] == result["total_chunks"]


# --- cover_letter _chroma_retrieve fallback ---


class TestChromaRetrieveFallback:
    @patch("app.services.embedding_service._get_model", return_value=_mock_model())
    def test_returns_none_when_empty(self, _mock, user_id):
        from app.services.cover_letter import _chroma_retrieve

        result = _chroma_retrieve(user_id, _SAMPLE_JD)
        assert result is None

    @patch("app.services.embedding_service._get_model", return_value=_mock_model())
    def test_returns_context_when_data_exists(self, _mock, user_id, source_id):
        from app.services.cover_letter import _chroma_retrieve
        from app.services.embedding_service import embed_document

        embed_document(user_id, "resume", source_id, _SAMPLE_RESUME)
        result = _chroma_retrieve(user_id, _SAMPLE_JD)
        assert result is not None
        context, chunks_used = result
        assert isinstance(context, str)
        assert chunks_used > 0
