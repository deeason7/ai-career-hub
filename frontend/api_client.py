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
    return getattr(requests, method)(f"{API_URL}{path}", headers=headers, **kwargs)


def safe_json(resp: requests.Response, fallback=None):
    """Safely parse JSON; returns fallback on decode errors (e.g. 502s)."""
    try:
        return resp.json()
    except Exception:
        return fallback


def detail(resp: requests.Response, default: str = "An unexpected error occurred.") -> str:
    """Extract error detail string from an error response, safely."""
    data = safe_json(resp, {})
    if isinstance(data, dict):
        return data.get("detail", default)
    return f"API error (HTTP {resp.status_code})"
