"""Public vector probes must not include provider messages or connection details."""

from unittest.mock import MagicMock

import pytest

from app.services.embedding_service import ChromaVectorStore, QdrantVectorStore


@pytest.mark.parametrize(
    ("store_type", "probe"),
    [(ChromaVectorStore, "heartbeat"), (QdrantVectorStore, "get_collections")],
)
def test_provider_failure_exposes_only_error_class(store_type, probe, caplog):
    client = MagicMock()
    getattr(client, probe).side_effect = RuntimeError("private-provider-host: access denied")

    result = store_type(client=client).healthcheck()

    assert result == {"status": "down", "detail": "RuntimeError"}
    assert "health check failed" in caplog.text
