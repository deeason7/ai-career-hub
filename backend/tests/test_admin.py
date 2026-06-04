"""Tests for the admin secret guard — constant-time compare and rejection paths."""

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.admin import _verify_admin_secret
from app.core.config import settings

_ADMIN_SECRET = "admin-secret-value-for-tests-1234567890"


def test_accepts_correct_secret(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_SECRET", _ADMIN_SECRET)
    assert _verify_admin_secret(_ADMIN_SECRET) is None


def test_rejects_wrong_secret(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_SECRET", _ADMIN_SECRET)
    with pytest.raises(HTTPException) as exc:
        _verify_admin_secret("not-the-secret")
    assert exc.value.status_code == 403


def test_missing_header_rejected_not_crashed(monkeypatch):
    # None must short-circuit to a 403, never reach compare_digest (which would TypeError).
    monkeypatch.setattr(settings, "ADMIN_SECRET", _ADMIN_SECRET)
    with pytest.raises(HTTPException) as exc:
        _verify_admin_secret(None)
    assert exc.value.status_code == 403


def test_unconfigured_secret_rejected(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_SECRET", "")
    with pytest.raises(HTTPException) as exc:
        _verify_admin_secret("anything")
    assert exc.value.status_code == 403
