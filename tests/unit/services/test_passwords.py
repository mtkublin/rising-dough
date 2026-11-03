"""Unit tests for ``services._passwords`` (T-D02a, ADR-0067)."""

from __future__ import annotations

import pytest

from budget_planner.services import _passwords
from budget_planner.services._passwords import (
    MAX_PASSWORD_BYTES,
    dummy_hash,
    hash_password,
    verify_password,
)

pytestmark = pytest.mark.unit

FAST = 4
SECRET = "correct horse battery staple"  # noqa: S105  # pragma: allowlist secret


def test_hash_round_trips() -> None:
    hashed = hash_password(SECRET, rounds=FAST)
    assert hashed.startswith("$2b$04$")
    assert verify_password(SECRET, hashed)


def test_hash_is_salted() -> None:
    assert hash_password(SECRET, rounds=FAST) != hash_password(SECRET, rounds=FAST)


def test_default_rounds_is_twelve_and_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _passwords.DEFAULT_ROUNDS == 12
    monkeypatch.setattr(_passwords, "DEFAULT_ROUNDS", 5)
    assert hash_password(SECRET).startswith("$2b$05$")


def test_wrong_password_is_rejected() -> None:
    assert not verify_password("wrong", hash_password(SECRET, rounds=FAST))


@pytest.mark.parametrize("bad_rounds", [3, 32])
def test_hash_rejects_out_of_range_rounds(bad_rounds: int) -> None:
    with pytest.raises(ValueError, match="rounds"):
        hash_password(SECRET, rounds=bad_rounds)


def test_hash_rejects_empty_password() -> None:
    with pytest.raises(ValueError, match="empty"):
        hash_password("", rounds=FAST)


def test_hash_rejects_overlong_password() -> None:
    with pytest.raises(ValueError, match="72"):
        hash_password("x" * (MAX_PASSWORD_BYTES + 1), rounds=FAST)


def test_hash_accepts_exactly_72_bytes() -> None:
    plain = "x" * MAX_PASSWORD_BYTES
    assert verify_password(plain, hash_password(plain, rounds=FAST))


@pytest.mark.parametrize(
    "hashed",
    [None, "", "not-a-bcrypt-hash", "$2b$04$short", "żółw-non-ascii"],
)
def test_verify_never_raises_on_malformed_hash(hashed: str | None) -> None:
    assert verify_password(SECRET, hashed) is False


def test_verify_returns_false_for_empty_or_overlong_password() -> None:
    hashed = hash_password(SECRET, rounds=FAST)
    assert verify_password("", hashed) is False
    assert verify_password("x" * (MAX_PASSWORD_BYTES + 1), hashed) is False


def test_dummy_hash_is_cached_per_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_passwords, "DEFAULT_ROUNDS", FAST)
    first = dummy_hash()
    assert first == dummy_hash()
    assert first.startswith("$2b$04$")
    assert verify_password("anything", first) is False
