"""Thin HTTP client — wraps requests with JWT injection and safe JSON parsing."""

import os

import requests
import streamlit as st

API_URL = os.environ.get("API_URL", "http://api:8000/api/v1")


def api(method: str, path: str, **kwargs) -> requests.Response:
    """Make an authenticated API call. Injects JWT from session state if present."""
    headers = kwargs.pop("headers", {})
    if st.session_state.get("token"):
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    kwargs.setdefault("timeout", 30)
    return getattr(requests, method)(f"{API_URL}{path}", headers=headers, **kwargs)


def safe_json(resp: requests.Response, fallback=None):
    """Safely parse JSON; returns fallback on decode errors (e.g. 502s)."""
    try:
        return resp.json()
    except Exception:
        return fallback


def detail(
    resp: requests.Response, default: str = "An unexpected error occurred."
) -> str:
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
                        msg = msg[len("Value error, "):]
                    msgs.append(msg)
            return "; ".join(msgs) if msgs else default
        if isinstance(d, str):
            return d
        return default
    return f"API error (HTTP {resp.status_code})"
