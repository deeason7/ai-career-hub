import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_REQUIRED_HEADERS = [
    ("x-content-type-options", "nosniff"),
    ("x-frame-options", "DENY"),
    ("referrer-policy", "strict-origin-when-cross-origin"),
    ("x-permitted-cross-domain-policies", "none"),
    ("cross-origin-resource-policy", "same-origin"),
    ("cross-origin-opener-policy", "same-origin"),
    ("content-security-policy", "default-src 'none'; frame-ancestors 'none'"),
]


@pytest.mark.parametrize("header,expected", _REQUIRED_HEADERS)
def test_security_header_present(header: str, expected: str) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get(header) == expected, (
        f"Missing or wrong value for {header!r}: got {resp.headers.get(header)!r}"
    )


def test_hsts_absent_in_non_production() -> None:
    resp = client.get("/health")
    assert "strict-transport-security" not in resp.headers


def test_permissions_policy_present() -> None:
    resp = client.get("/health")
    assert "permissions-policy" in resp.headers
    policy = resp.headers["permissions-policy"]
    for feature in ("geolocation", "microphone", "camera"):
        assert feature in policy


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
def test_docs_pages_relax_csp_for_assets(path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy", "")
    # The strict default-src 'none' would block Swagger/ReDoc's CDN assets.
    assert "cdn.jsdelivr.net" in csp
    assert csp != "default-src 'none'; frame-ancestors 'none'"
