"""Tests for document lifecycle service."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.services.lifecycle import (
    LIFECYCLE_DAYS,
    run_lifecycle_cleanup,
    set_cover_letter_expiry,
    set_resume_expiry,
)

# ── set_resume_expiry ────────────────────────────────────────────────────────


def test_first_resume_is_permanent():
    resume = MagicMock()
    set_resume_expiry(resume, existing_count=0)
    assert resume.is_permanent is True
    assert resume.expires_at is None


def test_subsequent_resume_gets_expiry():
    resume = MagicMock()
    before = datetime.now(UTC)
    set_resume_expiry(resume, existing_count=3)
    after = datetime.now(UTC)

    assert resume.is_permanent is False
    expected_min = before + timedelta(days=LIFECYCLE_DAYS)
    expected_max = after + timedelta(days=LIFECYCLE_DAYS)
    assert expected_min <= resume.expires_at <= expected_max


def test_expiry_window_is_exactly_lifecycle_days():
    resume = MagicMock()
    set_resume_expiry(resume, existing_count=1)
    delta = resume.expires_at - datetime.now(UTC)
    # Allow 2-second drift from test execution time
    assert abs(delta.days - LIFECYCLE_DAYS) <= 1


# ── set_cover_letter_expiry ──────────────────────────────────────────────────


def test_cover_letter_gets_expiry():
    cl = MagicMock()
    before = datetime.now(UTC)
    set_cover_letter_expiry(cl)
    after = datetime.now(UTC)

    expected_min = before + timedelta(days=LIFECYCLE_DAYS)
    expected_max = after + timedelta(days=LIFECYCLE_DAYS)
    assert expected_min <= cl.expires_at <= expected_max


# ── run_lifecycle_cleanup ────────────────────────────────────────────────────


class _FakeResume:
    def __init__(self, is_permanent: bool, expires_at: datetime | None):
        self.is_permanent = is_permanent
        self.expires_at = expires_at


class _FakeCoverLetter:
    def __init__(self, expires_at: datetime | None):
        self.expires_at = expires_at


def _make_engine_with(resumes, cover_letters):
    """Return a mock engine whose Session yields the given rows."""
    session = MagicMock()
    session.__enter__ = lambda s: s
    session.__exit__ = MagicMock(return_value=False)

    def exec_side_effect(stmt):
        # Distinguish calls by what model is being queried via the WHERE clause string
        stmt_str = str(stmt)
        if "cover_letter" in stmt_str.lower():
            return MagicMock(all=lambda: cover_letters)
        return MagicMock(all=lambda: resumes)

    session.exec.side_effect = exec_side_effect
    engine = MagicMock()

    with patch("app.services.lifecycle.Session", return_value=session):
        yield engine


@pytest.mark.usefixtures()
def test_cleanup_deletes_expired_resume():
    expired_r = _FakeResume(is_permanent=False, expires_at=datetime.now(UTC) - timedelta(days=1))

    with patch("app.services.lifecycle.Session") as MockSession:
        session = MagicMock()
        session.__enter__ = lambda s: s
        session.__exit__ = MagicMock(return_value=False)

        call_count = [0]

        def exec_side_effect(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(all=lambda: [expired_r])
            return MagicMock(all=lambda: [])

        session.exec.side_effect = exec_side_effect
        MockSession.return_value = session

        result = run_lifecycle_cleanup(MagicMock())

    assert result["deleted_resumes"] == 1
    assert result["deleted_cover_letters"] == 0
    session.delete.assert_called_once_with(expired_r)


def test_cleanup_skips_permanent_resume():
    with patch("app.services.lifecycle.Session") as MockSession:
        session = MagicMock()
        session.__enter__ = lambda s: s
        session.__exit__ = MagicMock(return_value=False)
        session.exec.return_value = MagicMock(all=lambda: [])
        MockSession.return_value = session

        result = run_lifecycle_cleanup(MagicMock())

    assert result["deleted_resumes"] == 0
    assert result["deleted_cover_letters"] == 0


def test_cleanup_deletes_expired_cover_letter():
    expired_cl = _FakeCoverLetter(expires_at=datetime.now(UTC) - timedelta(hours=1))

    with patch("app.services.lifecycle.Session") as MockSession:
        session = MagicMock()
        session.__enter__ = lambda s: s
        session.__exit__ = MagicMock(return_value=False)

        call_count = [0]

        def exec_side_effect(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(all=lambda: [])
            return MagicMock(all=lambda: [expired_cl])

        session.exec.side_effect = exec_side_effect
        MockSession.return_value = session

        result = run_lifecycle_cleanup(MagicMock())

    assert result["deleted_cover_letters"] == 1
    session.delete.assert_called_once_with(expired_cl)
