"""Thin HTTP client — wraps requests with JWT injection and safe JSON parsing."""

import os

import requests
import streamlit as st

API_URL = os.environ.get("API_URL", "http://api:8000/api/v1")


def _refresh_token() -> bool:
    """Mint a new access token from the stored refresh token; True on success.

    The refresh token lives only in server-side session state, so we resend it
    to the cookie-based /auth/refresh endpoint explicitly.
    """
    rt = st.session_state.get("refresh_token")
    if not rt:
        return False
    try:
        resp = requests.post(
            f"{API_URL}/auth/refresh",
            cookies={"refresh_token": rt},
            timeout=30,
        )
    except requests.exceptions.RequestException:
        return False
    if resp.status_code != 200:
        return False
    try:
        new_token = resp.json().get("access_token")
    except ValueError:
        return False
    if not new_token:
        return False
    st.session_state.token = new_token
    return True


def api(method: str, path: str, **kwargs) -> requests.Response:
    """Make an authenticated API call; refresh the access token once on a 401."""
    headers = kwargs.pop("headers", {})
    if st.session_state.get("token"):
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    kwargs.setdefault("timeout", 30)
    resp = getattr(requests, method)(f"{API_URL}{path}", headers=headers, **kwargs)
    if resp.status_code == 401 and path != "/auth/refresh" and _refresh_token():
        headers["Authorization"] = f"Bearer {st.session_state.token}"
        resp = getattr(requests, method)(f"{API_URL}{path}", headers=headers, **kwargs)
    return resp


def safe_json(resp: requests.Response, fallback=None):
    """Safely parse JSON; returns fallback on decode errors (e.g. 502s)."""
    try:
        return resp.json()
    except Exception:
        return fallback


def detail(resp: requests.Response, default: str = "An unexpected error occurred.") -> str:
    """Extract a human-readable error string from an API error response.

    Handles both FastAPI's standard {"detail": "string"} and Pydantic 422
    validation errors where detail is a list of dicts. Never returns raw
    input data (which may contain passwords).
    """
    data = safe_json(resp, {})
    if isinstance(data, dict):
        d = data.get("detail", default)
        if isinstance(d, list):
            msgs = []
            for err in d:
                if isinstance(err, dict) and "msg" in err:
                    msg = err["msg"]
                    # Strip Pydantic's "Value error, " prefix for cleaner display.
                    if msg.startswith("Value error, "):
                        msg = msg[len("Value error, ") :]
                    msgs.append(msg)
            return "; ".join(msgs) if msgs else default
        if isinstance(d, str):
            return d
        return default
    return f"API error (HTTP {resp.status_code})"
