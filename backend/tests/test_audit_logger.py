"""Tests for audit_logger.emit — happy path, exception swallow, and non-PII assertions."""

import hashlib
from unittest.mock import MagicMock, patch

from app.services.audit_logger import AuditLog, _hash_ip, emit


class TestHashIp:
    def test_returns_sha256_hex(self):
        result = _hash_ip("1.2.3.4")
        assert result == hashlib.sha256(b"1.2.3.4").hexdigest()

    def test_output_is_64_chars(self):
        assert len(_hash_ip("192.168.1.1")) == 64

    def test_different_ips_produce_different_hashes(self):
        assert _hash_ip("1.1.1.1") != _hash_ip("8.8.8.8")


def _make_mock_session():
    session = MagicMock()
    session.__enter__ = lambda s: s
    session.__exit__ = MagicMock(return_value=False)
    return session


class TestEmit:
    def test_happy_path_writes_audit_log(self):
        session = _make_mock_session()
        with patch("app.services.audit_logger.Session", return_value=session):
            emit("auth.login")

        session.add.assert_called_once()
        session.commit.assert_called_once()
        log: AuditLog = session.add.call_args[0][0]
        assert log.event == "auth.login"

    def test_ip_is_hashed_not_stored_raw(self):
        raw_ip = "203.0.113.42"
        request = MagicMock()
        request.client.host = raw_ip

        session = _make_mock_session()
        with patch("app.services.audit_logger.Session", return_value=session):
            emit("auth.login", request=request)

        log: AuditLog = session.add.call_args[0][0]
        assert log.ip_hash is not None
        assert raw_ip not in (log.ip_hash or "")
        assert log.ip_hash == _hash_ip(raw_ip)

    def test_metadata_contains_no_pii(self):
        import json
        import uuid

        user_id = uuid.uuid4()
        cover_letter_id = str(uuid.uuid4())

        session = _make_mock_session()
        with patch("app.services.audit_logger.Session", return_value=session):
            emit(
                "cover_letter.generate",
                user_id=user_id,
                metadata={"cover_letter_id": cover_letter_id},
            )

        log: AuditLog = session.add.call_args[0][0]
        meta = json.loads(log.metadata)
        # Only non-PII UUIDs allowed — no email, name, or resume text
        assert "email" not in meta
        assert "password" not in meta
        assert "raw_text" not in meta
        assert meta["cover_letter_id"] == cover_letter_id

    def test_emit_swallows_session_exception(self):
        """emit() must never raise even if the DB write fails."""
        with patch("app.services.audit_logger.Session", side_effect=RuntimeError("db down")):
            emit("auth.login")  # must not raise

    def test_emit_swallows_commit_exception(self):
        session = _make_mock_session()
        session.commit.side_effect = Exception("commit failed")
        with patch("app.services.audit_logger.Session", return_value=session):
            emit("resume.upload")  # must not raise

    def test_no_request_stores_no_ip_hash(self):
        session = _make_mock_session()
        with patch("app.services.audit_logger.Session", return_value=session):
            emit("cover_letter.generate", request=None)

        log: AuditLog = session.add.call_args[0][0]
        assert log.ip_hash is None

    def test_user_id_stored_on_log(self):
        import uuid

        user_id = uuid.uuid4()
        session = _make_mock_session()
        with patch("app.services.audit_logger.Session", return_value=session):
            emit("resume.upload", user_id=user_id)

        log: AuditLog = session.add.call_args[0][0]
        assert log.user_id == user_id
