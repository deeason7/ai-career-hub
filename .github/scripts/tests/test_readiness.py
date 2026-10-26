"""Regression coverage for deployment probes that previously reported false greens."""

import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "readiness", Path(__file__).resolve().parents[1] / "readiness.py"
)
readiness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readiness)


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
        def response(_opener, url):
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


if __name__ == "__main__":
    unittest.main()
