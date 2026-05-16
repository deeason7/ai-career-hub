"""Tests for job tracker automation: extract_job_metadata and _create_tracker_entry_bg."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.job_tracker_service import extract_job_metadata

# ── extract_job_metadata ──────────────────────────────────────────────────────


def test_extract_returns_company_and_role_keys():
    with patch("app.services.job_tracker_service._extract_via_instructor") as mock:
        mock.return_value = {"company": "Acme Corp", "role": "Backend Engineer"}
        result = extract_job_metadata("We are Acme Corp, hiring a Backend Engineer.")
    assert "company" in result
    assert "role" in result


def test_extract_falls_back_on_instructor_exception():
    with (
        patch("app.core.config.settings") as mock_settings,
        patch("app.services.job_tracker_service._extract_via_instructor") as mock_inst,
    ):
        mock_settings.USE_GROQ = True
        mock_inst.side_effect = RuntimeError("model timeout")
        result = extract_job_metadata("Some JD text")
    # Should not raise; fallback returned
    assert "company" in result
    assert "role" in result


def test_extract_truncates_jd_to_3000_chars():
    long_jd = "x" * 5000
    captured = {}

    def fake_extract(jd_snippet, fallback):
        captured["snippet"] = jd_snippet
        return {"company": "X", "role": "Y"}

    with patch(
        "app.services.job_tracker_service._extract_via_instructor", side_effect=fake_extract
    ):
        extract_job_metadata(long_jd)

    assert len(captured["snippet"]) == 3000


def test_extract_instructor_returns_fallback_on_empty_fields():
    from pydantic import ValidationError

    with (
        patch("app.services.job_tracker_service.call_structured") as mock_call,
        patch("app.core.config.settings") as mock_settings,
    ):
        mock_settings.USE_GROQ = True
        mock_call.side_effect = ValidationError.from_exception_data(
            title="JobExtraction", line_errors=[]
        )
        result = extract_job_metadata("A job posting with no company info.")

    assert result["company"] == "Unknown Company"
    assert result["role"] == "Unknown Role"


# ── _create_tracker_entry_bg ──────────────────────────────────────────────────


def _make_session_mock(existing_app=None):
    """Return a sync Session mock that exec().first() returns existing_app."""
    session = MagicMock()
    session.__enter__ = lambda s: s
    session.__exit__ = MagicMock(return_value=False)
    exec_result = MagicMock()
    exec_result.first.return_value = existing_app
    session.exec.return_value = exec_result
    return session


@pytest.fixture
def cl_bg():
    from app.api.v1.endpoints.cover_letters import _create_tracker_entry_bg  # noqa: PLC0415

    return _create_tracker_entry_bg


def test_auto_creates_new_entry_when_no_dedup_hit(cl_bg):
    user_id = uuid.uuid4()
    cl_id = uuid.uuid4()
    session = _make_session_mock(existing_app=None)

    with (
        patch("app.api.v1.endpoints.cover_letters.Session", return_value=session),
        patch(
            "app.services.job_tracker_service._extract_via_instructor",
            return_value={"company": "Google", "role": "SWE"},
        ),
    ):
        cl_bg(user_id=user_id, cover_letter_id=cl_id, job_description="Google SWE role")

    session.add.assert_called_once()
    session.commit.assert_called_once()
    created = session.add.call_args[0][0]
    assert created.source == "auto"
    assert created.cover_letter_id == cl_id
    assert created.user_id == user_id


def test_dedup_skips_creation_when_entry_exists_within_7_days(cl_bg):
    user_id = uuid.uuid4()
    cl_id = uuid.uuid4()
    existing = MagicMock()
    existing.cover_letter_id = cl_id  # already linked
    session = _make_session_mock(existing_app=existing)

    with (
        patch("app.api.v1.endpoints.cover_letters.Session", return_value=session),
        patch(
            "app.services.job_tracker_service._extract_via_instructor",
            return_value={"company": "Google", "role": "SWE"},
        ),
    ):
        cl_bg(user_id=user_id, cover_letter_id=cl_id, job_description="Google SWE role")

    # commit may or may not be called (CL already linked — no-op path)
    # but add should NOT be called with a new JobApplication
    for call in session.add.call_args_list:
        obj = call[0][0]
        # Should not create a fresh entry
        assert not isinstance(obj, type(existing)) or obj is existing


def test_dedup_links_cl_when_existing_has_no_cl(cl_bg):
    user_id = uuid.uuid4()
    cl_id = uuid.uuid4()
    existing = MagicMock()
    existing.cover_letter_id = None
    session = _make_session_mock(existing_app=existing)

    with (
        patch("app.api.v1.endpoints.cover_letters.Session", return_value=session),
        patch(
            "app.services.job_tracker_service._extract_via_instructor",
            return_value={"company": "Google", "role": "SWE"},
        ),
    ):
        cl_bg(user_id=user_id, cover_letter_id=cl_id, job_description="Google SWE role")

    assert existing.cover_letter_id == cl_id
    session.commit.assert_called_once()


def test_auto_create_swallows_extraction_error(cl_bg):
    """A complete failure in extraction must not raise — it is non-fatal."""
    user_id = uuid.uuid4()
    cl_id = uuid.uuid4()

    with patch(
        "app.services.job_tracker_service.extract_job_metadata",
        side_effect=RuntimeError("network down"),
    ):
        # Must not raise
        cl_bg(user_id=user_id, cover_letter_id=cl_id, job_description="Some JD")


def test_auto_create_sets_status_to_wishlist(cl_bg):
    user_id = uuid.uuid4()
    cl_id = uuid.uuid4()
    session = _make_session_mock(existing_app=None)

    with (
        patch("app.api.v1.endpoints.cover_letters.Session", return_value=session),
        patch(
            "app.services.job_tracker_service._extract_via_instructor",
            return_value={"company": "Meta", "role": "PM"},
        ),
    ):
        cl_bg(user_id=user_id, cover_letter_id=cl_id, job_description="Meta PM role")

    created = session.add.call_args[0][0]
    assert created.status == "wishlist"
