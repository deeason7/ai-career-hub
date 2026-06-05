"""SSRF guard tests for the job scraper: IP classification, host validation, redirect re-checks."""

import ipaddress
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.job_scraper import (
    JobFetchError,
    _assert_public_url,
    _get_validated,
    _is_blocked_ip,
)


def _ip(addr: str):
    return ipaddress.ip_address(addr)


def _fake_loop(getaddrinfo: AsyncMock) -> MagicMock:
    loop = MagicMock()
    loop.getaddrinfo = getaddrinfo
    return loop


def _resolving_to(addr: str) -> MagicMock:
    """Fake event loop whose DNS resolves any host to `addr`."""
    return _fake_loop(AsyncMock(return_value=[(0, 0, 0, "", (addr, 80))]))


def _redirect(location: str) -> MagicMock:
    resp = MagicMock()
    resp.is_redirect = True
    resp.headers = {"location": location}
    return resp


def _ok() -> MagicMock:
    resp = MagicMock()
    resp.is_redirect = False
    resp.headers = {}
    return resp


class TestIsBlockedIp:
    @pytest.mark.parametrize(
        "addr",
        [
            "127.0.0.1",  # loopback
            "::1",  # loopback (v6)
            "169.254.169.254",  # link-local — the cloud metadata endpoint (IMDS)
            "10.0.0.1",  # private
            "172.16.5.4",  # private
            "192.168.1.1",  # private
            "0.0.0.0",  # unspecified
            "224.0.0.1",  # multicast
            "fe80::1",  # link-local (v6)
            "fc00::1",  # unique-local (v6, private)
        ],
    )
    def test_blocks_internal_addresses(self, addr):
        assert _is_blocked_ip(_ip(addr)) is True

    @pytest.mark.parametrize(
        "addr", ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111"]
    )
    def test_allows_public_addresses(self, addr):
        assert _is_blocked_ip(_ip(addr)) is False


class TestAssertPublicUrl:
    async def test_rejects_non_http_scheme(self):
        # Scheme is rejected before any DNS lookup happens.
        with pytest.raises(JobFetchError, match="http"):
            await _assert_public_url("ftp://example.com/secret")

    async def test_rejects_host_resolving_to_metadata_ip(self):
        with patch("asyncio.get_running_loop", return_value=_resolving_to("169.254.169.254")):
            with pytest.raises(JobFetchError, match="not permitted"):
                await _assert_public_url("http://evil.example.com/")

    async def test_rejects_ipv4_mapped_internal_address(self):
        # ::ffff:169.254.169.254 must be unwrapped and judged as the IPv4 it embeds.
        with patch(
            "asyncio.get_running_loop", return_value=_resolving_to("::ffff:169.254.169.254")
        ):
            with pytest.raises(JobFetchError, match="not permitted"):
                await _assert_public_url("http://sneaky.example.com/")

    async def test_allows_public_host(self):
        with patch("asyncio.get_running_loop", return_value=_resolving_to("93.184.216.34")):
            await _assert_public_url("https://example.com/job/1")  # must not raise

    async def test_rejects_unresolvable_host(self):
        loop = _fake_loop(AsyncMock(side_effect=socket.gaierror))
        with patch("asyncio.get_running_loop", return_value=loop):
            with pytest.raises(JobFetchError, match="resolve"):
                await _assert_public_url("http://nope.invalid/")


class TestRedirectValidation:
    async def test_redirect_into_internal_address_is_blocked(self):
        # example.com is public but 302s to the metadata IP — the hop must be re-validated
        # and rejected before we ever fetch it.
        def resolve(host, port, **_):
            addr = "93.184.216.34" if host == "example.com" else "169.254.169.254"
            return [(0, 0, 0, "", (addr, port))]

        loop = _fake_loop(AsyncMock(side_effect=resolve))
        client = MagicMock()
        client.get = AsyncMock(return_value=_redirect("http://169.254.169.254/latest/meta-data/"))

        with patch("asyncio.get_running_loop", return_value=loop):
            with pytest.raises(JobFetchError, match="not permitted"):
                await _get_validated(client, "http://example.com/job/1")

        client.get.assert_awaited_once()  # the internal target was never fetched

    async def test_too_many_redirects(self):
        loop = _resolving_to("93.184.216.34")
        client = MagicMock()
        client.get = AsyncMock(return_value=_redirect("http://example.com/loop"))

        with patch("asyncio.get_running_loop", return_value=loop):
            with pytest.raises(JobFetchError, match="redirect"):
                await _get_validated(client, "http://example.com/start")

    async def test_returns_final_non_redirect_response(self):
        loop = _resolving_to("93.184.216.34")
        final = _ok()
        client = MagicMock()
        client.get = AsyncMock(return_value=final)

        with patch("asyncio.get_running_loop", return_value=loop):
            result = await _get_validated(client, "https://example.com/job/1")

        assert result is final
