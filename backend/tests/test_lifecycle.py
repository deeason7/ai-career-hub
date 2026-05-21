"""Tests for document lifecycle service."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.lifecycle import (
    LIFECYCLE_DAYS,
    promote_to_permanent,
    run_lifecycle_cleanup,
    set_cover_letter_expiry,
    set_resume_expiry,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


class _Resume:
    def __init__(self, *, is_permanent: bool, expires_at: datetime | None, user_id=None):
        self.id = uuid.uuid4()
        self.user_id = user_id or uuid.uuid4()
        self.is_permanent = is_permanent
        self.expires_at = expires_at


class _CoverLetter:
    def __init__(self, *, expires_at: datetime | None):
        self.expires_at = expires_at


def _mock_session(resume_rows=None, cl_rows=None):
    """Return a patched Session context manager yielding controlled query results."""
    session = MagicMock()
    session.__enter__ = lambda s: s
    session.__exit__ = MagicMock(return_value=False)

    call_index = [0]
    results = [resume_rows or [], cl_rows or []]

    def _exec(stmt):
        idx = min(call_index[0], len(results) - 1)
        call_index[0] += 1
        return MagicMock(all=lambda r=results[idx]: r)

    session.exec.side_effect = _exec
    return session


# ── set_resume_expiry ────────────────────────────────────────────────────────


def test_first_resume_marked_permanent():
    resume = MagicMock()
    set_resume_expiry(resume, existing_count=0)
    assert resume.is_permanent is True
    assert resume.expires_at is None


def test_second_resume_not_permanent():
    resume = MagicMock()
    set_resume_expiry(resume, existing_count=1)
    assert resume.is_permanent is False


def test_subsequent_resume_receives_expiry():
    resume = MagicMock()
    before = datetime.now(UTC)
    set_resume_expiry(resume, existing_count=2)
    after = datetime.now(UTC)
    assert before + timedelta(days=LIFECYCLE_DAYS) <= resume.expires_at
    assert resume.expires_at <= after + timedelta(days=LIFECYCLE_DAYS)


def test_expiry_is_utc_aware():
    resume = MagicMock()
    set_resume_expiry(resume, existing_count=1)
    assert resume.expires_at.tzinfo is not None


def test_expiry_duration_matches_constant():
    resume = MagicMock()
    set_resume_expiry(resume, existing_count=5)
    delta = resume.expires_at - datetime.now(UTC)
    assert LIFECYCLE_DAYS - 1 <= delta.days <= LIFECYCLE_DAYS


# ── set_cover_letter_expiry ──────────────────────────────────────────────────


def test_cover_letter_receives_expiry():
    cl = MagicMock()
    before = datetime.now(UTC)
    set_cover_letter_expiry(cl)
    after = datetime.now(UTC)
    assert before + timedelta(days=LIFECYCLE_DAYS) <= cl.expires_at
    assert cl.expires_at <= after + timedelta(days=LIFECYCLE_DAYS)


def test_cover_letter_expiry_is_utc_aware():
    cl = MagicMock()
    set_cover_letter_expiry(cl)
    assert cl.expires_at.tzinfo is not None


def test_cover_letter_expiry_duration():
    cl = MagicMock()
    set_cover_letter_expiry(cl)
    delta = cl.expires_at - datetime.now(UTC)
    assert LIFECYCLE_DAYS - 1 <= delta.days <= LIFECYCLE_DAYS


# ── promote_to_permanent ─────────────────────────────────────────────────────


def test_promote_updates_resume():
    user_id = uuid.uuid4()
    resume = _Resume(is_permanent=False, expires_at=datetime.now(UTC), user_id=user_id)

    session = MagicMock()
    session.__enter__ = lambda s: s
    session.__exit__ = MagicMock(return_value=False)
    session.get.return_value = resume

    with patch("app.services.lifecycle.Session", return_value=session):
        result = promote_to_permanent(resume.id, user_id, MagicMock())

    assert result is True
    assert resume.is_permanent is True
    assert resume.expires_at is None
    session.commit.assert_called_once()


def test_promote_returns_false_for_unknown_id():
    session = MagicMock()
    session.__enter__ = lambda s: s
    session.__exit__ = MagicMock(return_value=False)
    session.get.return_value = None

    with patch("app.services.lifecycle.Session", return_value=session):
        result = promote_to_permanent(uuid.uuid4(), uuid.uuid4(), MagicMock())

    assert result is False
    session.commit.assert_not_called()


def test_promote_returns_false_for_wrong_user():
    owner_id = uuid.uuid4()
    resume = _Resume(is_permanent=False, expires_at=None, user_id=owner_id)

    session = MagicMock()
    session.__enter__ = lambda s: s
    session.__exit__ = MagicMock(return_value=False)
    session.get.return_value = resume

    with patch("app.services.lifecycle.Session", return_value=session):
        result = promote_to_permanent(resume.id, uuid.uuid4(), MagicMock())

    assert result is False
    session.commit.assert_not_called()


# ── run_lifecycle_cleanup ────────────────────────────────────────────────────


def test_cleanup_returns_zero_when_nothing_expired():
    session = _mock_session(resume_rows=[], cl_rows=[])
    with patch("app.services.lifecycle.Session", return_value=session):
        result = run_lifecycle_cleanup(MagicMock())
    assert result == {"deleted_resumes": 0, "deleted_cover_letters": 0}


def test_cleanup_deletes_expired_non_permanent_resume():
    expired = _Resume(is_permanent=False, expires_at=datetime.now(UTC) - timedelta(hours=1))
    session = _mock_session(resume_rows=[expired], cl_rows=[])
    with patch("app.services.lifecycle.Session", return_value=session):
        result = run_lifecycle_cleanup(MagicMock())
    assert result["deleted_resumes"] == 1
    session.delete.assert_any_call(expired)


def test_cleanup_does_not_delete_future_resume():
    session = _mock_session(resume_rows=[], cl_rows=[])
    with patch("app.services.lifecycle.Session", return_value=session):
        result = run_lifecycle_cleanup(MagicMock())
    assert result["deleted_resumes"] == 0
    session.delete.assert_not_called()


def test_cleanup_deletes_expired_cover_letter():
    expired = _CoverLetter(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    session = _mock_session(resume_rows=[], cl_rows=[expired])
    with patch("app.services.lifecycle.Session", return_value=session):
        result = run_lifecycle_cleanup(MagicMock())
    assert result["deleted_cover_letters"] == 1
    session.delete.assert_any_call(expired)


def test_cleanup_does_not_delete_future_cover_letter():
    session = _mock_session(resume_rows=[], cl_rows=[])
    with patch("app.services.lifecycle.Session", return_value=session):
        result = run_lifecycle_cleanup(MagicMock())
    assert result["deleted_cover_letters"] == 0
    session.delete.assert_not_called()


def test_cleanup_counts_multiple_deletions():
    r1 = _Resume(is_permanent=False, expires_at=datetime.now(UTC) - timedelta(days=1))
    r2 = _Resume(is_permanent=False, expires_at=datetime.now(UTC) - timedelta(days=2))
    c1 = _CoverLetter(expires_at=datetime.now(UTC) - timedelta(days=1))
    c2 = _CoverLetter(expires_at=datetime.now(UTC) - timedelta(hours=3))
    session = _mock_session(resume_rows=[r1, r2], cl_rows=[c1, c2])
    with patch("app.services.lifecycle.Session", return_value=session):
        result = run_lifecycle_cleanup(MagicMock())
    assert result["deleted_resumes"] == 2
    assert result["deleted_cover_letters"] == 2
    assert session.delete.call_count == 4


def test_cleanup_commits_exactly_once():
    session = _mock_session()
    with patch("app.services.lifecycle.Session", return_value=session):
        run_lifecycle_cleanup(MagicMock())
    session.commit.assert_called_once()


def test_cleanup_result_has_correct_keys():
    session = _mock_session()
    with patch("app.services.lifecycle.Session", return_value=session):
        result = run_lifecycle_cleanup(MagicMock())
    assert set(result.keys()) == {"deleted_resumes", "deleted_cover_letters"}
