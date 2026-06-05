"""Tests for the RAG search endpoint."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient

# rag_search imports retrieve_context lazily inside the handler, so patch the
# definition site rather than the endpoint module.
_RETRIEVE_PATCH = "app.services.embedding_service.retrieve_context"


@pytest.mark.asyncio
async def test_rag_search_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/rag/search", json={"query": "python"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rag_search_rejects_empty_query(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/rag/search", json={"query": "   "}, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rag_search_returns_results(client: AsyncClient, auth_headers: dict):
    fake = [
        {
            "chunk_text": "Python developer",
            "source_type": "resume",
            "source_id": "abc123",
            "chunk_index": 0,
            "distance": 0.12,
        }
    ]
    with patch(_RETRIEVE_PATCH, return_value=fake):
        resp = await client.post(
            "/api/v1/rag/search",
            json={"query": "python", "top_k": 3},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source_type"] == "resume"
