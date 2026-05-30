import pytest
from pydantic import ValidationError

from app.models.user import UserCreate


def _make(password: str, email: str = "test@example.com") -> UserCreate:
    return UserCreate(email=email, password=password)


# ── Length boundary ──────────────────────────────────────────────────────────


def test_password_minimum_12_chars_accepted() -> None:
    u = _make("Abcdefghij1!")
    assert u.password == "Abcdefghij1!"


def test_password_11_chars_rejected() -> None:
    with pytest.raises(ValidationError):
        _make("Abcdefghi1!")


def test_password_exactly_12_chars_accepted() -> None:
    u = _make("Abcdefghij1!")
    assert len(u.password) == 12


def test_password_longer_than_12_accepted() -> None:
    u = _make("CorrectHorseBattery1!")
    assert len(u.password) > 12


# ── Digit requirement ────────────────────────────────────────────────────────


def test_password_without_digit_rejected() -> None:
    with pytest.raises(ValidationError, match="digit"):
        _make("AbcdefghijkL!")


def test_password_with_digit_accepted() -> None:
    u = _make("Abcdefghij1!")
    assert any(c.isdigit() for c in u.password)


# ── Uppercase / symbol requirement ───────────────────────────────────────────


def test_password_all_lowercase_rejected() -> None:
    with pytest.raises(ValidationError):
        _make("abcdefghijkl1")  # no uppercase, no symbol


def test_password_with_uppercase_accepted() -> None:
    u = _make("Abcdefghij1!")
    assert any(c.isupper() for c in u.password)


def test_password_with_symbol_only_uppercase_requirement_accepted() -> None:
    u = _make("abcdefghij1!@")
    assert u.password == "abcdefghij1!@"


# ── Email-match rejection ────────────────────────────────────────────────────


def test_password_matching_email_rejected() -> None:
    with pytest.raises(ValidationError, match="email"):
        _make("test@example.com", email="test@example.com")


def test_password_not_matching_email_accepted() -> None:
    u = _make("Abcdefghij1!", email="test@example.com")
    assert u.password != u.email


# ── Email format validation ──────────────────────────────────────────────────


def test_invalid_email_rejected() -> None:
    with pytest.raises(ValidationError):
        _make("Abcdefghij1!", email="not-an-email")


def test_valid_email_accepted() -> None:
    u = _make("Abcdefghij1!", email="user@domain.co.uk")
    assert u.email == "user@domain.co.uk"
