"""Tests for document lifecycle service."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.services.lifecycle import (
    LIFECYCLE_DAYS,
    promote_to_permanent,
    reap_stuck_cover_letters,
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


# ── reap_stuck_cover_letters ─────────────────────────────────────────────────


class _ProcessingCL:
    def __init__(self):
        self.status = "processing"


def _reaper_session(stuck_rows):
    session = MagicMock()
    session.__enter__ = lambda s: s
    session.__exit__ = MagicMock(return_value=False)
    session.exec.return_value = MagicMock(all=lambda: stuck_rows)
    return session


def test_reaper_fails_stuck_cover_letters():
    stuck = [_ProcessingCL(), _ProcessingCL()]
    session = _reaper_session(stuck)
    with patch("app.services.lifecycle.Session", return_value=session):
        reaped = reap_stuck_cover_letters(MagicMock())
    assert reaped == 2
    assert all(cl.status == "failure" for cl in stuck)
    session.commit.assert_called_once()


def test_reaper_returns_zero_when_none_stuck():
    session = _reaper_session([])
    with patch("app.services.lifecycle.Session", return_value=session):
        reaped = reap_stuck_cover_letters(MagicMock())
    assert reaped == 0
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_reaper_marks_only_old_processing_rows(client, auth_headers):
    """Real DB: an old 'processing' row is failed; a fresh one is left alone."""
    import io

    from sqlmodel import Session

    from app.core.db import sync_engine
    from app.models.cover_letter import CoverLetter
    from app.models.resume import Resume

    up = await client.post(
        "/api/v1/resumes/upload",
        files={"file": ("r.txt", io.BytesIO(b"Python developer with FastAPI."), "text/plain")},
        data={"name": "Reaper Resume"},
        headers=auth_headers,
    )
    assert up.status_code == 201
    resume_id = uuid.UUID(up.json()["id"])

    with Session(sync_engine) as session:
        user_id = session.get(Resume, resume_id).user_id
        old = CoverLetter(
            user_id=user_id,
            resume_id=resume_id,
            job_description="stuck",
            task_id=str(uuid.uuid4()),
            status="processing",
            started_at=datetime.now(UTC) - timedelta(minutes=30),
        )
        fresh = CoverLetter(
            user_id=user_id,
            resume_id=resume_id,
            job_description="fresh",
            task_id=str(uuid.uuid4()),
            status="processing",
            started_at=datetime.now(UTC),
        )
        session.add(old)
        session.add(fresh)
        session.commit()
        old_id, fresh_id = old.id, fresh.id

    reaped = reap_stuck_cover_letters(sync_engine, max_age_minutes=15)
    assert reaped >= 1

    with Session(sync_engine) as session:
        assert session.get(CoverLetter, old_id).status == "failure"
        assert session.get(CoverLetter, fresh_id).status == "processing"


# ── Cascade behaviour (real DB) ──────────────────────────────────────────────
# The mocked cases above never exercise a foreign key. Deleting a parent whose
# children carry a NOT NULL FK is precisely where the ORM's default "unlink the
# children" behaviour blows up, so these two run against Postgres.


@pytest.mark.asyncio
async def test_cleanup_removes_expired_letter_with_its_revisions(active_resume):
    """An expired letter takes its revision rows with it."""
    from sqlmodel import Session

    from app.core.db import sync_engine
    from app.models.cover_letter import CoverLetter
    from app.models.cover_letter_revision import CoverLetterRevision
    from app.models.resume import Resume

    resume_id = uuid.UUID(active_resume)
    with Session(sync_engine) as session:
        letter = CoverLetter(
            user_id=session.get(Resume, resume_id).user_id,
            resume_id=resume_id,
            job_description="expired letter",
            generated_text="v0",
            status="completed",
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        session.add(letter)
        session.commit()
        session.refresh(letter)
        revision = CoverLetterRevision(
            cover_letter_id=letter.id,
            version_number=1,
            generated_text="v1",
            user_command="make it shorter",
        )
        session.add(revision)
        session.commit()
        letter_id, revision_id = letter.id, revision.id

    run_lifecycle_cleanup(sync_engine)

    with Session(sync_engine) as session:
        assert session.get(CoverLetter, letter_id) is None
        assert session.get(CoverLetterRevision, revision_id) is None


@pytest.mark.asyncio
async def test_cleanup_removes_expired_resume_with_attached_letters(active_resume):
    """An expired resume takes its cover letters with it, expired or not."""
    from sqlmodel import Session

    from app.core.db import sync_engine
    from app.models.cover_letter import CoverLetter
    from app.models.resume import Resume

    resume_id = uuid.UUID(active_resume)
    with Session(sync_engine) as session:
        resume = session.get(Resume, resume_id)
        resume.is_permanent = False
        resume.expires_at = datetime.now(UTC) - timedelta(days=1)
        letter = CoverLetter(
            user_id=resume.user_id,
            resume_id=resume_id,
            job_description="still well inside its own TTL",
            expires_at=datetime.now(UTC) + timedelta(days=LIFECYCLE_DAYS),
        )
        session.add(resume)
        session.add(letter)
        session.commit()
        letter_id = letter.id

    run_lifecycle_cleanup(sync_engine)

    with Session(sync_engine) as session:
        assert session.get(Resume, resume_id) is None
        assert session.get(CoverLetter, letter_id) is None
