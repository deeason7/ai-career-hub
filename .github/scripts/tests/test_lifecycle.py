"""Regression coverage for the scheduled cleanup client without production writes."""

import contextlib
import importlib.util
import io
import json
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

SPEC = importlib.util.spec_from_file_location(
    "lifecycle_client", Path(__file__).resolve().parents[1] / "lifecycle.py"
)
lifecycle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lifecycle)


def healthy() -> dict:
    return {
        "status": "ok",
        "deleted_resumes": 2,
        "deleted_cover_letters": 3,
        "reaped_stuck_cover_letters": 0,
    }


def response(body: bytes, status: int = 200) -> MagicMock:
    result = MagicMock()
    result.status = status
    result.headers = {"Content-Length": str(len(body))}
    result.read.return_value = body
    result.__enter__.return_value = result
    return result


class LifecycleTests(unittest.TestCase):
    def test_success_posts_once_and_returns_only_counts(self):
        payload = {**healthy(), "private_detail": "do-not-log"}
        with patch.object(lifecycle.urllib.request, "build_opener") as build:
            build.return_value.open.return_value = response(json.dumps(payload).encode())
            result = lifecycle.cleanup("https://api.example/", "synthetic-secret")
        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["deleted_resumes"], 2)
        self.assertNotIn("private_detail", json.dumps(result))
        build.return_value.open.assert_called_once()
        request = build.return_value.open.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, "https://api.example/api/v1/admin/lifecycle/run")
        self.assertEqual(request.get_header("X-admin-secret"), "synthetic-secret")
        self.assertEqual(build.return_value.open.call_args.kwargs["timeout"], 60)

    def test_missing_secret_invalid_url_or_timeout_never_sends_request(self):
        for base, secret, timeout in (
            ("https://api.example", "", 60),
            ("https://api.example", "   ", 60),
            ("https://api.example", "secret\nheader", 60),
            ("file:///tmp/local", "secret", 60),
            ("https://user:secret@api.example", "secret", 60),
            ("https://api.example?secret=value", "secret", 60),
            ("https://api.example/#fragment", "secret", 60),
            ("https://api.example\n", "secret", 60),
            ("https://api.example", "secret", 0),
            ("https://api.example", "secret", 61),
            ("https://api.example", "secret", float("nan")),
        ):
            with self.subTest(base=base, timeout=timeout):
                with patch.object(lifecycle.urllib.request, "build_opener") as build:
                    self.assertFalse(lifecycle.cleanup(base, secret, timeout)["ok"])
                build.assert_not_called()

    def test_redirects_are_rejected_without_forwarding_secret(self):
        handler = lifecycle.NoRedirect()
        request = urllib.request.Request("https://api.example/", method="POST")
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                self.assertIsNone(
                    handler.redirect_request(
                        request, None, status, "redirect", {}, "https://other.example/"
                    )
                )
                with patch.object(lifecycle.urllib.request, "build_opener") as build:
                    build.return_value.open.side_effect = urllib.error.HTTPError(
                        "https://api.example/private", status, "redirect", {}, io.BytesIO(b"")
                    )
                    result = lifecycle.cleanup("https://api.example", "synthetic-secret")
                self.assertFalse(result["ok"])
                self.assertEqual(result["http_status"], status)
                build.return_value.open.assert_called_once()

    def test_http_200_with_html_or_invalid_contract_stays_red(self):
        payloads = [
            b"<html>provider error</html>",
            b"[]",
            b"{}",
            json.dumps({**healthy(), "status": "down"}).encode(),
        ]
        for field in lifecycle.COUNT_FIELDS:
            for value in (None, True, -1, "1", 0.5):
                payloads.append(json.dumps({**healthy(), field: value}).encode())
        for body in payloads:
            with self.subTest(body=body):
                with patch.object(lifecycle.urllib.request, "build_opener") as build:
                    build.return_value.open.return_value = response(body)
                    self.assertFalse(lifecycle.cleanup("https://api.example", "secret")["ok"])

    def test_non_200_and_oversize_responses_fail(self):
        for status, body in ((201, b"{}"), (503, b"{}"), (200, b"x" * 65537)):
            with self.subTest(status=status):
                with patch.object(lifecycle.urllib.request, "build_opener") as build:
                    build.return_value.open.return_value = response(body, status)
                    self.assertFalse(lifecycle.cleanup("https://api.example", "secret")["ok"])

    def test_error_reports_only_http_status_and_allowlisted_exception_class(self):
        for detail, expected in (
            ("Lifecycle cleanup failed: NotNullViolation", "NotNullViolation"),
            ("Lifecycle cleanup failed: secret at https://private.example", None),
            ("private database password", None),
        ):
            with self.subTest(detail=detail):
                with patch.object(lifecycle.urllib.request, "build_opener") as build:
                    build.return_value.open.side_effect = urllib.error.HTTPError(
                        "https://api.example/private?token=private-value",
                        500,
                        "private-value",
                        {},
                        io.BytesIO(json.dumps({"detail": detail}).encode()),
                    )
                    result = lifecycle.cleanup("https://api.example", "synthetic-secret")
                self.assertFalse(result["ok"])
                self.assertEqual(result.get("error_class"), expected)
                self.assertNotIn("private", json.dumps(result))
                self.assertNotIn("synthetic-secret", json.dumps(result))

    def test_transport_failure_does_not_retry_uncertain_post(self):
        for error in (
            TimeoutError("private-value"),
            urllib.error.URLError("https://private.example"),
            OSError("synthetic-secret"),
        ):
            with self.subTest(error=type(error).__name__):
                with patch.object(lifecycle.urllib.request, "build_opener") as build:
                    build.return_value.open.side_effect = error
                    result = lifecycle.cleanup("https://api.example", "synthetic-secret")
                self.assertFalse(result["ok"])
                self.assertNotIn("private", json.dumps(result))
                self.assertNotIn("synthetic-secret", json.dumps(result))
                build.return_value.open.assert_called_once()

    def test_truncated_response_is_not_reported_as_success(self):
        body = json.dumps(healthy()).encode()
        result = response(body)
        result.headers["Content-Length"] = str(len(body) + 1)
        with patch.object(lifecycle.urllib.request, "build_opener") as build:
            build.return_value.open.return_value = result
            self.assertFalse(lifecycle.cleanup("https://api.example", "synthetic-secret")["ok"])

    def test_cli_uses_environment_secret_and_exit_status(self):
        for ok, expected in ((True, 0), (False, 1)):
            output = io.StringIO()
            with (
                patch.dict(lifecycle.os.environ, {"ADMIN_SECRET": "synthetic-secret"}),
                patch.object(lifecycle, "cleanup", return_value={"ok": ok}) as cleanup,
                contextlib.redirect_stdout(output),
            ):
                code = lifecycle.main(["--api-base", "https://api.example", "--timeout", "30"])
            self.assertEqual(code, expected)
            cleanup.assert_called_once_with("https://api.example", "synthetic-secret", 30)
            self.assertEqual(json.loads(output.getvalue()), {"ok": ok})


if __name__ == "__main__":
    unittest.main()
