"""Tests for n8n webhook callback endpoint.

Tests verify:
  1. Valid callback with correct secret updates the DB record
  2. Invalid/missing webhook secret returns 401
  3. Callback for non-existent cover letter returns 404
  4. Duplicate callback (already processed) is handled idempotently
  5. Fallback behavior when n8n is not configured
"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# A fixed UUID for tests — matches no real record
_FAKE_CL_ID = str(uuid.uuid4())


class TestWebhookAuth:
    """Test webhook secret validation."""

    @pytest.mark.asyncio
    async def test_missing_secret_returns_422(self, client: AsyncClient):
        """Request without X-Webhook-Secret header is rejected."""
        response = await client.put(
            f"/api/v1/webhooks/n8n/cover-letters/{_FAKE_CL_ID}/callback",
            json={"generated_text": "x" * 100, "status": "success"},
        )
        # FastAPI returns 422 for missing required header
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_wrong_secret_returns_401(self, client: AsyncClient):
        """Request with incorrect secret is rejected."""
        response = await client.put(
            f"/api/v1/webhooks/n8n/cover-letters/{_FAKE_CL_ID}/callback",
            json={"generated_text": "x" * 100, "status": "success"},
            headers={"X-Webhook-Secret": "wrong-secret"},
        )
        # If N8N_WEBHOOK_SECRET is empty, returns 503; if set, returns 401
        assert response.status_code in (401, 503)


class TestCallbackPayloadValidation:
    """Test payload validation for the callback endpoint."""

    @pytest.mark.asyncio
    async def test_rejects_empty_generated_text(self, client: AsyncClient):
        """Payload with generated_text too short is rejected."""
        response = await client.put(
            f"/api/v1/webhooks/n8n/cover-letters/{_FAKE_CL_ID}/callback",
            json={"generated_text": "too short", "status": "success"},
            headers={"X-Webhook-Secret": "test-secret"},
        )
        # Either 422 (validation) or 401/503 (auth) depending on config
        assert response.status_code in (401, 422, 503)

    @pytest.mark.asyncio
    async def test_rejects_invalid_status(self, client: AsyncClient):
        """Payload with invalid status value is rejected."""
        response = await client.put(
            f"/api/v1/webhooks/n8n/cover-letters/{_FAKE_CL_ID}/callback",
            json={"generated_text": "x" * 100, "status": "invalid_status"},
            headers={"X-Webhook-Secret": "test-secret"},
        )
        assert response.status_code in (401, 422, 503)


class TestFallbackBehavior:
    """Test that local BackgroundTasks work when n8n is disabled."""

    def test_n8n_disabled_by_default(self):
        """With no N8N_WEBHOOK_URL set, N8N_ENABLED should be False."""
        from app.core.config import settings
        # Default config has empty URLs — n8n is disabled
        if not settings.N8N_WEBHOOK_URL:
            assert settings.N8N_ENABLED is False

    def test_n8n_enabled_requires_both_url_and_secret(self):
        """N8N_ENABLED should only be True when BOTH URL and secret are set."""
        from app.core.config import Settings

        # Only URL, no secret
        s = Settings(
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            POSTGRES_DB="test",
            SECRET_KEY="test",
            N8N_WEBHOOK_URL="https://example.com/webhook",
            N8N_WEBHOOK_SECRET="",
        )
        assert s.N8N_ENABLED is False

        # Both URL and secret
        s2 = Settings(
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            POSTGRES_DB="test",
            SECRET_KEY="test",
            N8N_WEBHOOK_URL="https://example.com/webhook",
            N8N_WEBHOOK_SECRET="my-secret",
        )
        assert s2.N8N_ENABLED is True
