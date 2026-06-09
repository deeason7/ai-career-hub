"""Smoke tests — verify all page modules and shared utilities import cleanly."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_streamlit(monkeypatch):
    monkeypatch.setattr("streamlit.session_state", {"token": None, "user": None}, raising=False)
    monkeypatch.setattr("streamlit_cookies_controller.CookieController", MagicMock, raising=False)


class TestModuleImports:
    def test_api_client_imports(self):
        with patch.dict("os.environ", {"API_URL": "http://localhost:8000/api/v1"}):
            from api_client import API_URL, api, detail, safe_json  # noqa: F401

            assert API_URL == "http://localhost:8000/api/v1"

    def test_components_imports(self):
        from components import (  # noqa: F401
            lifecycle_badge,
            loading_spinner,
            show_error,
            show_success,
            toast_error,
            toast_success,
        )

    def test_session_imports(self):
        from session import cookie_get, cookie_remove, cookie_set  # noqa: F401

    def test_ui_imports(self):
        from ui import (  # noqa: F401
            card,
            chip_row,
            empty_state,
            error_state,
            loading,
            metric_tile,
            nav_to,
            page_header,
            score_gauge,
            section,
            status_icon,
            status_pill,
        )

    def test_ui_reexports_keepers(self):
        # ui is the single import surface — keepers stay reachable through it.
        from ui import (  # noqa: F401
            job_description_input,
            lifecycle_badge,
            loading_spinner,
            render_qa_scores,
        )

    def test_status_icon_known_and_unknown(self):
        from ui import status_icon

        assert status_icon("offer") == "🎉"
        assert status_icon("not_a_status") == "•"

    def test_tracker_applied_stamp(self):
        # applied_at is stamped exactly once: first transition into "applied".
        from views.job_tracker import _applied_stamp

        body = _applied_stamp({"applied_at": None}, "applied")
        assert body["status"] == "applied"
        assert "applied_at" in body
        assert "applied_at" not in _applied_stamp({"applied_at": "2026-06-01"}, "applied")
        assert "applied_at" not in _applied_stamp({}, "interview")

    def test_score_tone_thresholds(self):
        from ui import score_tone

        assert score_tone(85) == "good"
        assert score_tone(55) == "warn"
        assert score_tone(20) == "bad"

    def test_error_state_classify(self):
        # The honest-error mapping behind error_state: never collapse 401/5xx to "cold".
        from ui import _classify

        assert _classify(401) == "auth"
        assert _classify(403) == "auth"
        assert _classify(429) == "rate"
        assert _classify(503) == "cold"
        assert _classify(None) == "network"
        assert _classify(500) == "server"

    def test_generate_poll_outcome(self):
        # One tick of the generate poll: terminal vs transient classification.
        from views.cover_letter import _GENERATE_TIMEOUT_S, _poll_outcome

        assert _poll_outcome(404, None, 5) == "lost"
        assert _poll_outcome(401, None, 5) == "auth"
        assert _poll_outcome(200, "SUCCESS", 5) == "done"
        assert _poll_outcome(200, "FAILURE", 5) == "failed"
        assert _poll_outcome(200, "STARTED", 5) == "running"
        assert _poll_outcome(200, "PENDING", 5) == "running"
        assert _poll_outcome(None, None, 5) == "running"  # network blip = transient
        assert _poll_outcome(200, "STARTED", _GENERATE_TIMEOUT_S + 1) == "timeout"

    def test_lifecycle_badge_expired(self):
        from components import lifecycle_badge

        result = lifecycle_badge("2020-01-01T00:00:00Z")
        assert "expired" in result or "🔴" in result

    def test_lifecycle_badge_permanent(self):
        from components import lifecycle_badge

        result = lifecycle_badge(None, is_permanent=True)
        assert "permanent" in result

    def test_lifecycle_badge_no_expiry(self):
        from components import lifecycle_badge

        result = lifecycle_badge(None)
        assert result == ""

    def test_views_dashboard_importable(self):
        import importlib

        importlib.import_module("views.dashboard")

    def test_views_resumes_importable(self):
        import importlib

        importlib.import_module("views.resumes")

    def test_views_cover_letter_importable(self):
        import importlib

        importlib.import_module("views.cover_letter")

    def test_views_job_match_importable(self):
        import importlib

        importlib.import_module("views.job_match")

    def test_views_job_tracker_importable(self):
        import importlib

        importlib.import_module("views.job_tracker")

    def test_views_legal_importable(self):
        import importlib

        importlib.import_module("views.legal")

    def test_views_agent_importable(self):
        import importlib

        importlib.import_module("views.agent")
