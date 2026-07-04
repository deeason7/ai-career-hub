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

    def test_onboarding_steps_done_flags(self):
        # Each milestone's done flag mirrors account state; nav keys are stable.
        from ui import onboarding_steps

        steps = onboarding_steps(has_resume=True, has_letter=False, has_applied=False)
        assert [s["done"] for s in steps] == [True, False, False]
        assert [s["nav"] for s in steps] == ["resumes", "agent", "tracker"]

    def test_onboarding_active_step(self):
        # The active step is the first not-done one; None once fully onboarded.
        from ui import _active_step, onboarding_steps

        assert _active_step(onboarding_steps(False, False, False)) == 0
        assert _active_step(onboarding_steps(True, False, False)) == 1
        assert _active_step(onboarding_steps(True, True, False)) == 2
        assert _active_step(onboarding_steps(True, True, True)) is None

    def test_poll_outcome(self):
        # One tick of a task poll: terminal vs transient classification.
        from ui import poll_outcome

        assert poll_outcome(404, None, 5, 180) == "lost"
        assert poll_outcome(401, None, 5, 180) == "auth"
        assert poll_outcome(200, "SUCCESS", 5, 180) == "done"
        assert poll_outcome(200, "FAILURE", 5, 180) == "failed"
        assert poll_outcome(200, "STARTED", 5, 180) == "running"
        assert poll_outcome(200, "PENDING", 5, 180) == "running"
        assert poll_outcome(None, None, 5, 180) == "running"  # network blip = transient
        assert poll_outcome(503, None, 5, 180) == "running"  # store hiccup = transient
        assert poll_outcome(200, "STARTED", 181, 180) == "timeout"

    def test_agent_step_states(self):
        # The strip and the checklist share one state map: first pending runs.
        from views.agent import _step_states

        states = _step_states({"scrape_job": "success"}, True)
        assert states["scrape_job"] == "success"
        assert states["extract_metadata"] == "running"
        assert list(states.values()).count("running") == 1
        assert all(s == "pending" for s in _step_states({}, False).values())

    def test_pipeline_html_states(self):
        from ui import _pipeline_html

        html = _pipeline_html(
            [
                {"icon": "🔗", "label": "scrape", "state": "done"},
                {"icon": "🏷️", "label": "extract", "state": "running"},
                {"icon": "🔎", "label": "research", "state": "pending"},
            ]
        )
        assert html.count("ch-pn-done") == 1
        assert html.count("ch-pn-running") == 1
        assert html.count("ch-pl-link") == 2  # connectors between nodes only

    def test_score_hero_html(self):
        # Ring target + per-part tracks; values clamp into 0–100.
        from ui import _score_hero_html

        html = _score_hero_html(
            82, [{"label": "Semantic", "value": 74, "note": "50% weight"}], "ATS match"
        )
        assert "--target:82%" in html
        assert "--w:74%" in html and "50% weight" in html
        assert "ATS match" in html
        assert "--target:100%" in _score_hero_html(140, [], "x")

    def test_agent_checklist(self):
        # The first pending step shows as running — but only while the task runs.
        from views.agent import _agent_checklist

        lines = _agent_checklist({"scrape_job": "success", "extract_metadata": "failed"}, True)
        assert lines[0].startswith("✅")
        assert lines[1].startswith("❌")
        assert lines[2].startswith("⏳")  # first pending becomes the running marker
        assert lines[3].startswith("⬜")  # only one running marker
        assert len(lines) == 7

        idle = _agent_checklist({}, False)
        assert all(line.startswith("⬜") for line in idle)

    def test_job_match_steps_line(self):
        # Live step captions render in pipeline order with honest state icons.
        from views.job_match import _steps_line

        line = _steps_line({"ats": "done", "skill_gap": "running", "interview": "pending"})
        assert line == "✅ ATS score · ⏳ Skill gap · ⬜ Interview questions"
        assert "❌" in _steps_line({"ats": "failed"})
        # A rate-limited step says so instead of posing as ordinary progress.
        assert "model busy" in _steps_line({"ats": "waiting"})
        # Unknown states and missing steps degrade to the pending icon.
        assert _steps_line({}) == "⬜ ATS score · ⬜ Skill gap · ⬜ Interview questions"

    def test_refine_lineage_tag(self):
        # History titles show where a branch came from; root revisions stay unmarked.
        from views.cover_letter import _lineage_tag

        versions = {"abc": 2}
        assert _lineage_tag({"parent_revision_id": "abc"}, versions) == " ← v2"
        assert _lineage_tag({"parent_revision_id": None}, versions) == ""
        assert _lineage_tag({}, versions) == ""
        # Parent no longer in the list (SET NULL edge) → no broken label.
        assert _lineage_tag({"parent_revision_id": "gone"}, versions) == ""

    def test_resumes_parse_failed_flag(self):
        # The upload response carries parsed_json as a string; bad shapes are calm.
        from views.resumes import _parse_failed

        assert _parse_failed({"parsed_json": '{"parse_failed": true}'}) is True
        assert _parse_failed({"parsed_json": '{"skills": ["python"]}'}) is False
        assert _parse_failed({"parsed_json": None}) is False
        assert _parse_failed({"parsed_json": "not json"}) is False
        assert _parse_failed({}) is False

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

    def test_tour_importable(self):
        import importlib

        importlib.import_module("tour")

    def test_showcase_importable(self):
        import importlib

        importlib.import_module("showcase")

    def test_tour_steps_use_registered_nav_keys(self):
        # Every step must point at a key app.py registers, or Next strands the user.
        from tour import STEPS

        nav_keys = {"home", "agent", "resumes", "job_match", "cover_letter", "tracker", "legal"}
        assert {s["page"] for s in STEPS} <= nav_keys
        # The route opens and closes on Home.
        assert STEPS[0]["page"] == "home"
        assert STEPS[-1]["page"] == "home"

    def test_tour_resync(self):
        # On-route stays put; off-route hides; wandering lands on the nearest step.
        from tour import STEPS, _resync

        assert _resync(2, STEPS[2]["page"]) == 2
        assert _resync(2, "legal") is None
        assert _resync(1, "home") == 0  # early wander home → the opening step
        assert _resync(len(STEPS) - 2, "home") == len(STEPS) - 1  # late → the finale

    def test_seed_shared_jd(self):
        # Seeding fills the shared JD and drops each page's stale widget copy.
        import streamlit as st

        from components import seed_shared_jd

        st.session_state["jd_input_job_match"] = "stale"
        seed_shared_jd("fresh jd")
        assert st.session_state["shared_jd"] == "fresh jd"
        assert "jd_input_job_match" not in st.session_state

    def test_showcase_covers_every_feature(self):
        # The landing story names each core surface of the product.
        from showcase import _page_html

        page = _page_html().lower()
        for needle in ("resume", "ats", "cover letter", "skill gap", "quick apply", "tracker"):
            assert needle in page

    def test_tour_prompt_once_per_session(self, monkeypatch):
        # The welcome dialog fires once; an active or dismissed tour suppresses it.
        import streamlit as st

        import tour

        shown = []
        monkeypatch.setattr(tour, "_prompt_dialog", lambda: shown.append(1))
        tour.prompt()
        tour.prompt()
        assert len(shown) == 1
        st.session_state.clear()
        st.session_state["tour_step"] = 3
        tour.prompt()
        assert len(shown) == 1

    def test_landing_overlay_once_per_session(self, monkeypatch):
        # Closing is CSS-only (invisible to the server), so the overlay must
        # render exactly once; the next rerun falls back to the inline story.
        import streamlit as st

        import showcase

        calls = []
        monkeypatch.setattr(st, "html", lambda body: calls.append(body))
        showcase.render_overlay()
        showcase.render_overlay()
        assert len(calls) == 1
        assert 'id="ch-dismiss"' in calls[0]
        # Both close triggers point at the same checkbox: the ✕ pill + the CTA.
        assert calls[0].count('for="ch-dismiss"') == 2
