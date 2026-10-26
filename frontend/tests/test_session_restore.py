"""Temporary profile failures must not invalidate a returning user's sign-in."""

import json
from unittest.mock import patch

import pytest
import requests
import streamlit as st

from api_client import _refresh_token, current_user


class _SessionState(dict):
    __getattr__ = dict.__getitem__


def response(status: int, body: dict | list) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body).encode()
    return result


@pytest.mark.parametrize("status", [401, 403])
def test_auth_rejection_invalidates_session(status):
    with patch("api_client.api", return_value=response(status, {})):
        assert current_user() is None


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_service_error_remains_retryable(status):
    with (
        patch("api_client.api", return_value=response(status, {})),
        pytest.raises(requests.HTTPError),
    ):
        current_user()


def test_network_error_remains_retryable():
    with (
        patch("api_client.api", side_effect=requests.Timeout),
        pytest.raises(requests.Timeout),
    ):
        current_user()


@pytest.mark.parametrize("body", [{}, [], {"detail": "Service starting"}])
def test_unexpected_profile_remains_retryable(body):
    with (
        patch("api_client.api", return_value=response(200, body)),
        pytest.raises(requests.RequestException),
    ):
        current_user()


def test_profile_load_returns_authenticated_user():
    user = {"email": "jordan@example.com", "full_name": "Jordan"}
    with patch("api_client.api", return_value=response(200, user)) as request:
        assert current_user() == user
    request.assert_called_once_with("get", "/auth/me", timeout=10)


@pytest.mark.parametrize("status", [429, 500, 503])
def test_refresh_service_failure_does_not_look_like_expired_credentials(status, monkeypatch):
    state = _SessionState(token="expired-access", refresh_token="still-valid-refresh")
    monkeypatch.setattr(st, "session_state", state)
    with (
        patch("api_client.requests.get", return_value=response(401, {})),
        patch("api_client.requests.post", return_value=response(status, {})),
        pytest.raises(requests.HTTPError),
    ):
        current_user()
    assert state == {"token": "expired-access", "refresh_token": "still-valid-refresh"}


def test_refresh_network_failure_preserves_credentials(monkeypatch):
    state = {"refresh_token": "still-valid-refresh"}
    monkeypatch.setattr(st, "session_state", state)
    with (
        patch("api_client.requests.post", side_effect=requests.Timeout),
        pytest.raises(requests.Timeout),
    ):
        _refresh_token()
    assert state["refresh_token"] == "still-valid-refresh"


def test_expired_refresh_requires_login(monkeypatch):
    monkeypatch.setattr(st, "session_state", {"refresh_token": "expired-refresh"})
    with patch("api_client.requests.post", return_value=response(401, {})):
        assert _refresh_token() is False
