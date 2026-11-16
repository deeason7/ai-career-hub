"""Regression coverage for deployment probes that previously reported false greens."""

import contextlib
import importlib.util
import io
import json
import os
import socket
import threading
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "readiness", Path(__file__).resolve().parents[1] / "readiness.py"
)
readiness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readiness)
SENTINEL = "private-provider-session-do-not-log"


def healthy() -> dict:
    return {
        "api": "ok",
        "db": {"status": "ok"},
        "redis": {"status": "ok"},
        "vector": {"status": "ok"},
        "semantic": {"status": "ok"},
    }


class ReadinessTests(unittest.TestCase):
    def test_every_required_dependency_can_fail_the_gate(self):
        for name in ("db", "redis", "vector", "semantic"):
            with self.subTest(name=name):
                body = healthy()
                body[name] = {"status": "down"}
                self.assertTrue(readiness.dependency_problems(body))

    def test_missing_semantic_signal_is_not_healthy(self):
        body = healthy()
        del body["semantic"]
        self.assertIn("semantic: missing health signal", readiness.dependency_problems(body))

    def test_only_redis_may_be_disabled(self):
        body = healthy()
        body["redis"] = "disabled"
        self.assertEqual(readiness.dependency_problems(body), [])
        body["db"] = "disabled"
        self.assertTrue(readiness.dependency_problems(body))

    def test_invalid_health_body_is_not_healthy(self):
        for body in (None, [], {}, "ok"):
            with self.subTest(body=body):
                self.assertTrue(readiness.dependency_problems(body))

    def test_sleeping_and_error_pages_are_not_running(self):
        for status in (None, 0, 12, 13, 14):
            with self.subTest(status=status):
                self.assertTrue(readiness.streamlit_problems({"status": status}))
        self.assertEqual(readiness.streamlit_problems({"status": 5}), [])
        self.assertIn("asleep", readiness.streamlit_problems({"status": 12})[0])

    def test_zero_semantic_similarity_with_live_model_is_valid(self):
        body = {"score": 0, "semantic_score": 0, "breakdown": {"semantic_weight": 0.5}}
        self.assertEqual(readiness.ats_problems(body), [])

    def test_plausible_composite_cannot_hide_dead_semantic_channel(self):
        for weight in (None, 0, -1, True, float("nan"), float("inf"), "0.5"):
            with self.subTest(weight=weight):
                body = {"score": 66.8, "breakdown": {"semantic_weight": weight}}
                self.assertTrue(readiness.ats_problems(body))

    def test_invalid_composite_fails_even_with_live_model(self):
        for score in (True, None, -1, 101, float("nan")):
            with self.subTest(score=score):
                self.assertTrue(
                    readiness.ats_problems({"score": score, "breakdown": {"semantic_weight": 0.5}})
                )

    def test_frontend_checked_even_when_api_is_down(self):
        def response(_opener, url, **_kwargs):
            if "health/warm" in url:
                raise TimeoutError
            return json.dumps({"status": 12}).encode()

        with patch.object(readiness, "get", side_effect=response) as get:
            result = readiness.probe("https://api.example", "https://demo.streamlit.app", None)
        self.assertFalse(result["ok"])
        self.assertEqual(get.call_count, 2)
        self.assertIn("asleep", result["checks"]["frontend"]["problems"][0])

    def test_old_release_cannot_pass_deployment_gate(self):
        with patch.object(
            readiness, "get", side_effect=[json.dumps(healthy()).encode(), b'{"version":"4.4.3"}']
        ):
            result = readiness.probe("https://api.example", None, "4.4.4")
        self.assertFalse(result["ok"])
        self.assertIn("expected 4.4.4", result["checks"]["api"]["problems"][0])

    def test_html_error_page_is_not_a_healthy_local_streamlit(self):
        with patch.object(readiness, "get", return_value=b"<html>asleep</html>"):
            result = readiness.probe(None, "http://localhost:8501", None)
        self.assertFalse(result["ok"])

    def test_healthy_api_and_frontend_pass(self):
        with patch.object(
            readiness, "get", side_effect=[json.dumps(healthy()).encode(), b'{"status":5}', b"ok"]
        ):
            result = readiness.probe("https://api.example", "https://demo.streamlit.app", None)
        self.assertTrue(result["ok"])

    def test_running_control_plane_with_broken_runtime_fails(self):
        with patch.object(
            readiness, "get", side_effect=[b'{"status":5}', b"<html>provider error</html>"]
        ) as get:
            result = readiness.probe(None, "https://demo.streamlit.app", None)
        self.assertFalse(result["ok"])
        self.assertEqual(get.call_args.args[1], "https://demo.streamlit.app/~/+/_stcore/health")

    def test_missing_semantic_requires_explicit_keepwarm_compatibility(self):
        body = healthy()
        del body["semantic"]
        self.assertTrue(readiness.dependency_problems(body))
        self.assertEqual(readiness.dependency_problems(body, allow_missing_semantic=True), [])
        for state in ("down", "disabled", None, {}, {"status": "down"}):
            with self.subTest(state=state):
                body["semantic"] = state
                self.assertTrue(readiness.dependency_problems(body, allow_missing_semantic=True))

    def test_keepwarm_compatibility_does_not_allow_missing_datastores(self):
        for name in ("db", "redis", "vector"):
            with self.subTest(name=name):
                body = healthy()
                del body[name]
                self.assertTrue(readiness.dependency_problems(body, allow_missing_semantic=True))

    def test_legacy_health_emits_warning_only_with_explicit_compatibility(self):
        body = healthy()
        del body["semantic"]
        with patch.object(readiness, "get", return_value=json.dumps(body).encode()):
            strict = readiness.probe("https://api.example", None, None)
        with patch.object(
            readiness, "get", side_effect=[json.dumps(body).encode(), b'{"version":"4.4.3"}']
        ):
            compatible = readiness.probe(
                "https://api.example", None, None, allow_missing_semantic=True
            )
        self.assertFalse(strict["ok"])
        self.assertTrue(compatible["ok"])
        self.assertTrue(compatible["checks"]["api"]["warnings"])

    def test_newer_release_cannot_use_legacy_semantic_exception(self):
        body = healthy()
        del body["semantic"]
        with patch.object(
            readiness, "get", side_effect=[json.dumps(body).encode(), b'{"version":"4.4.4"}']
        ):
            result = readiness.probe("https://api.example", None, None, allow_missing_semantic=True)
        self.assertFalse(result["ok"])

    def test_dependency_and_runtime_diagnostics_hide_provider_values(self):
        body = healthy()
        body["db"] = {"status": SENTINEL, "detail": SENTINEL}
        messages = readiness.dependency_problems(body)
        messages += readiness.streamlit_problems({"status": SENTINEL})
        self.assertTrue(messages)
        self.assertNotIn(SENTINEL, json.dumps(messages))

    def test_version_diagnostics_hide_untrusted_provider_values(self):
        with patch.object(
            readiness,
            "get",
            side_effect=[
                json.dumps(healthy()).encode(),
                json.dumps({"version": SENTINEL}).encode(),
            ],
        ):
            result = readiness.probe("https://api.example", None, "4.4.4")
        self.assertFalse(result["ok"])
        self.assertNotIn(SENTINEL, json.dumps(result))

    def run_retry_scenario(self, *, recover):
        counts = {"api": 0, "frontend": 0}

        def response(api, frontend, _version, **_kwargs):
            checks = {}
            for name, base in (("api", api), ("frontend", frontend)):
                if base is None:
                    continue
                counts[name] += 1
                ok = name == "frontend" or (recover and counts[name] > 1)
                checks[name] = {
                    "ok": ok,
                    "problems": [] if ok else ["API is not ready"],
                    "warnings": [],
                    "http_status": 200,
                }
            return {"ok": all(check["ok"] for check in checks.values()), "checks": checks}

        argv = [
            "readiness.py",
            "--api-base",
            "https://api.example",
            "--frontend-url",
            "https://demo.streamlit.app",
            "--attempts",
            "3",
            "--retry-delay",
            "0",
        ]
        with (
            patch("sys.argv", argv),
            patch.object(readiness, "probe", side_effect=response),
            patch.object(readiness.time, "sleep"),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            code = readiness.main()
        return code, counts, output.getvalue()

    def test_retries_preserve_successful_service_without_repeating_it(self):
        code, counts, output = self.run_retry_scenario(recover=True)
        self.assertEqual(code, 0)
        self.assertEqual(counts, {"api": 2, "frontend": 1})
        self.assertIn("frontend", output)

    def test_persistent_failure_exhausts_attempts_and_returns_nonzero(self):
        code, counts, output = self.run_retry_scenario(recover=False)
        self.assertEqual(code, 1)
        self.assertEqual(counts, {"api": 3, "frontend": 1})
        self.assertIn("frontend", output)

    def test_nonfinite_timing_arguments_are_rejected(self):
        for option in ("--retry-delay", "--request-timeout"):
            for value in ("nan", "inf", "-inf"):
                with (
                    self.subTest(option=option, value=value),
                    patch(
                        "sys.argv",
                        ["readiness.py", "--api-base", "https://api.example", f"{option}={value}"],
                    ),
                    contextlib.redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit) as caught,
                ):
                    readiness.main()
                self.assertEqual(caught.exception.code, 2)


class ProbeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format, *_args):
        pass

    def reply(self, status, body=b"ok", headers=None):
        self.send_response(status)
        self.send_header("Connection", "close")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/redirect":
            self.reply(
                303,
                b"",
                {
                    "Location": f"/cookie-required?session={SENTINEL}",
                    "Set-Cookie": f"viewer={SENTINEL}; Path=/; HttpOnly",
                },
            )
        elif path in ("/cookie-required", "/cookie-followup"):
            status = 200 if f"viewer={SENTINEL}" in self.headers.get("Cookie", "") else 403
            self.reply(status)
        elif path == "/loop":
            self.reply(303, b"", {"Location": f"/loop?session={SENTINEL}"})
        elif path == "/bad-redirect":
            self.reply(303, b"", {"Location": f"file:///private/{SENTINEL}"})
        elif path == "/upgrade":
            self.reply(101, b"", {"Connection": "Upgrade", "Upgrade": "websocket"})
        elif path.startswith("/status/"):
            self.reply(int(path.split("/")[2]), SENTINEL.encode())
        elif path == "/truncated":
            self.send_response(200)
            self.send_header("Content-Length", "999")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b"ok")
            self.close_connection = True
        elif path == "/oversize":
            self.reply(200, b" " * (1024 * 1024 + 1))
        elif path == "/disconnect":
            self.connection.shutdown(socket.SHUT_RDWR)
            self.close_connection = True
        elif path == "/slow":
            time.sleep(0.15)
            self.reply(200)
        else:
            self.reply(200)


class ReadinessTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ProbeHandler)
        except PermissionError as exc:
            if os.environ.get("CAREERHUB_REQUIRE_NETWORK_TESTS") == "1":
                raise
            raise unittest.SkipTest("this sandbox prohibits binding a loopback server") from exc
        cls.server.daemon_threads = True
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def opener(self):
        # Ignore workstation proxy settings for deterministic loopback transactions.
        with patch.dict("os.environ", {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}):
            return readiness.build_opener()

    def test_plain_200_response_succeeds(self):
        self.assertEqual(readiness.get(self.opener(), f"{self.base}/ok", timeout=1), b"ok")

    def test_redirect_cookie_survives_followup_request(self):
        opener = self.opener()
        self.assertEqual(readiness.get(opener, f"{self.base}/redirect", timeout=1), b"ok")
        self.assertEqual(readiness.get(opener, f"{self.base}/cookie-followup", timeout=1), b"ok")
        with self.assertRaises(readiness.ProbeError):
            readiness.get(self.opener(), f"{self.base}/cookie-followup", timeout=1)

    def test_http_failure_preserves_status_and_hides_body(self):
        for status in (403, 500, 503):
            with self.subTest(status=status), self.assertRaises(readiness.ProbeError) as caught:
                readiness.get(self.opener(), f"{self.base}/status/{status}", timeout=1)
            self.assertEqual(caught.exception.http_status, status)
            self.assertNotIn(SENTINEL, str(caught.exception))

    def test_upgrade_is_not_an_http_health_success(self):
        with self.assertRaises(readiness.ProbeError) as caught:
            readiness.get(self.opener(), f"{self.base}/upgrade", timeout=1)
        self.assertEqual(caught.exception.http_status, 101)

    def test_redirect_loop_and_unsupported_scheme_fail_safely(self):
        for path in ("/loop", "/bad-redirect"):
            with self.subTest(path=path), self.assertRaises(readiness.ProbeError) as caught:
                readiness.get(self.opener(), f"{self.base}{path}", timeout=1)
            self.assertNotIn(SENTINEL, str(caught.exception))

    def test_truncated_body_is_not_healthy(self):
        with self.assertRaises(readiness.ProbeError):
            readiness.get(self.opener(), f"{self.base}/truncated", timeout=1)

    def test_oversize_body_is_rejected(self):
        with self.assertRaises(readiness.ProbeError):
            readiness.get(self.opener(), f"{self.base}/oversize", timeout=1)

    def test_disconnect_is_a_transport_failure(self):
        with self.assertRaises(readiness.ProbeError) as caught:
            readiness.get(self.opener(), f"{self.base}/disconnect", timeout=1)
        self.assertIsNone(caught.exception.http_status)

    def test_timeout_is_a_transport_failure(self):
        with self.assertRaises(readiness.ProbeError) as caught:
            readiness.get(self.opener(), f"{self.base}/slow", timeout=0.03)
        self.assertIsNone(caught.exception.http_status)

    def test_refused_connection_is_a_transport_failure(self):
        with socket.socket() as closed:
            closed.bind(("127.0.0.1", 0))
            port = closed.getsockname()[1]
        with self.assertRaises(readiness.ProbeError) as caught:
            readiness.get(self.opener(), f"http://127.0.0.1:{port}", timeout=1)
        self.assertIsNone(caught.exception.http_status)

    def test_probe_failure_keeps_http_status_and_safe_diagnostic(self):
        result = readiness.probe(f"{self.base}/status/503", None, None, request_timeout=1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["checks"]["api"]["http_status"], 503)
        self.assertNotIn(SENTINEL, json.dumps(result))

    def test_transport_exception_text_is_not_logged(self):
        opener = self.opener()
        with (
            patch.object(opener, "open", side_effect=OSError(SENTINEL)),
            self.assertRaises(readiness.ProbeError) as caught,
        ):
            readiness.get(opener, f"{self.base}/ok", timeout=1)
        self.assertIsNone(caught.exception.http_status)
        self.assertNotIn(SENTINEL, str(caught.exception))


class MemorySocket:
    """Feed actual HTTP bytes through urllib without requiring a local listener."""

    def __init__(self, router):
        self.router = router
        self.sent = bytearray()

    def sendall(self, data):
        self.sent.extend(data)

    def setsockopt(self, *_args):
        pass

    def close(self):
        pass

    def makefile(self, *_args, **_kwargs):
        return io.BytesIO(self.router(bytes(self.sent)))


def wire_response(status=200, body=b"ok", headers=None):
    fields = {"Content-Length": str(len(body)), "Connection": "close", **(headers or {})}
    head = f"HTTP/1.1 {status} Result\r\n" + "".join(
        f"{name}: {value}\r\n" for name, value in fields.items()
    )
    return head.encode() + b"\r\n" + body


class ReadinessWireTests(unittest.TestCase):
    @contextlib.contextmanager
    def client(self, router):
        # Only the socket boundary is replaced; HTTP parsing, cookies, redirects,
        # status handling and body validation run through their real code.
        with (
            patch("urllib.request.getproxies", return_value={}),
            patch("socket.create_connection", side_effect=lambda *_a, **_k: MemorySocket(router)),
        ):
            yield readiness.build_opener()

    def test_cookie_redirect_and_next_request_use_the_same_jar(self):
        requests = []

        def router(request):
            requests.append(request)
            if b"GET /start " in request:
                return wire_response(
                    303,
                    b"",
                    {
                        "Location": f"/health?session={SENTINEL}",
                        "Set-Cookie": f"viewer={SENTINEL}; Path=/; HttpOnly",
                    },
                )
            status = 200 if f"Cookie: viewer={SENTINEL}".encode() in request else 403
            return wire_response(status)

        with self.client(router) as opener:
            self.assertEqual(readiness.get(opener, "http://viewer.example/start"), b"ok")
            self.assertEqual(readiness.get(opener, "http://viewer.example/next"), b"ok")
        self.assertEqual(len(requests), 3)

    def test_every_http_failure_and_upgrade_remains_a_failure(self):
        for status in (101, 401, 403, 404, 429, 500, 503):
            with (
                self.subTest(status=status),
                self.client(
                    lambda _request, status=status: wire_response(status, SENTINEL.encode())
                ) as opener,
            ):
                with self.assertRaises(readiness.ProbeError) as caught:
                    readiness.get(opener, "http://viewer.example/health")
                self.assertEqual(caught.exception.http_status, status)
                self.assertNotIn(SENTINEL, str(caught.exception))

    def test_bad_framing_and_oversize_do_not_pass_as_ok(self):
        for response in (
            wire_response(body=b"ok", headers={"Content-Length": "999"}),
            wire_response(body=b"ok", headers={"Content-Length": "invalid"}),
            wire_response(body=b" " * (readiness.MAX_BODY_BYTES + 1)),
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\nok\r\n",
        ):
            with (
                self.subTest(length=len(response)),
                self.client(lambda _request, response=response: response) as opener,
            ):
                with self.assertRaises(readiness.ProbeError) as caught:
                    readiness.get(opener, "http://viewer.example/health")
                self.assertEqual(caught.exception.http_status, 200)

    def test_redirect_loop_is_bounded_and_secret_safe(self):
        requests = []

        def router(request):
            requests.append(request)
            return wire_response(303, b"", {"Location": f"/loop?session={SENTINEL}"})

        with self.client(router) as opener, self.assertRaises(readiness.ProbeError) as caught:
            readiness.get(opener, "http://viewer.example/loop")
        self.assertLessEqual(len(requests), readiness.MAX_REDIRECTS + 2)
        self.assertNotIn(SENTINEL, str(caught.exception))

    def test_redirect_to_file_is_rejected(self):
        with (
            self.client(
                lambda _request: wire_response(303, b"", {"Location": f"file:///{SENTINEL}"})
            ) as opener,
            self.assertRaises(readiness.ProbeError) as caught,
        ):
            readiness.get(opener, "http://viewer.example/health")
        self.assertEqual(caught.exception.http_status, 303)
        self.assertNotIn(SENTINEL, str(caught.exception))

    def test_invalid_json_preserves_http_200_without_leaking_body(self):
        with self.client(lambda _request: wire_response(body=SENTINEL.encode())):
            result = readiness.probe("http://api.example", None, None)
        self.assertFalse(result["ok"])
        self.assertEqual(result["checks"]["api"]["http_status"], 200)
        self.assertNotIn(SENTINEL, json.dumps(result))

    def test_frontend_viewer_and_runtime_both_checked_over_http(self):
        paths = []

        def router(request):
            path = request.split(b" ")[1]
            paths.append(path)
            if path == b"/api/v2/app/status":
                return wire_response(
                    body=b'{"status":5}', headers={"Set-Cookie": "viewer=ok; Path=/"}
                )
            status = 200 if b"Cookie: viewer=ok" in request else 403
            return wire_response(status)

        with self.client(router):
            result = readiness.probe(None, "http://demo.streamlit.app", None)
        self.assertTrue(result["ok"])
        self.assertEqual(paths, [b"/api/v2/app/status", b"/~/+/_stcore/health"])

    def test_transport_failure_has_no_invented_http_status(self):
        for error in (OSError(SENTINEL), TimeoutError(SENTINEL)):
            with patch("socket.create_connection", side_effect=error):
                result = readiness.probe("http://api.example", None, None)
            self.assertFalse(result["ok"])
            self.assertIsNone(result["checks"]["api"]["http_status"])
            self.assertNotIn(SENTINEL, json.dumps(result))


if __name__ == "__main__":
    unittest.main()
