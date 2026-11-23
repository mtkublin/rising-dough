"""Unit tests for the bcrypt ``PasswordHasher`` adapter (T-Q291, ADR-0021 amendment, ADR-0067).

Real bcrypt on purpose: the adapter is the one place that owns it. Services are tested with
``tests.auth_support.FakePasswordHasher``.
"""

from __future__ import annotations

import bcrypt
import pytest

from budget_planner.adapters import bcrypt_hasher
from budget_planner.adapters.bcrypt_hasher import BcryptHasher
from budget_planner.domain.ports import MAX_PASSWORD_BYTES

pytestmark = pytest.mark.unit

FAST = BcryptHasher(rounds=4)
SECRET = "correct horse battery staple"  # noqa: S105  # pragma: allowlist secret


def test_hash_round_trips_at_the_configured_cost() -> None:
    hashed = FAST.hash(SECRET)
    assert hashed.startswith("$2b$04$")
    assert FAST.verify(SECRET, hashed) is True


def test_hash_is_salted() -> None:
    assert FAST.hash(SECRET) != FAST.hash(SECRET)


def test_production_default_cost_is_twelve() -> None:
    assert BcryptHasher().rounds == 12
    assert bcrypt_hasher.DEFAULT_ROUNDS == 12


def test_wrong_password_is_rejected() -> None:
    assert FAST.verify("wrong", FAST.hash(SECRET)) is False


@pytest.mark.parametrize("bad_rounds", [3, 32])
def test_rounds_out_of_range_are_rejected(bad_rounds: int) -> None:
    with pytest.raises(ValueError, match="rounds"):
        BcryptHasher(rounds=bad_rounds)


def test_hash_rejects_empty_password() -> None:
    with pytest.raises(ValueError, match="empty"):
        FAST.hash("")


def test_hash_rejects_overlong_password() -> None:
    with pytest.raises(ValueError, match="72"):
        FAST.hash("x" * (MAX_PASSWORD_BYTES + 1))


def test_hash_accepts_exactly_72_bytes() -> None:
    plain = "x" * MAX_PASSWORD_BYTES
    assert FAST.verify(plain, FAST.hash(plain)) is True


@pytest.mark.parametrize(
    "hashed",
    [None, "", "not-a-bcrypt-hash", "$2b$04$short", "żółw-non-ascii"],
)
def test_verify_never_raises_on_malformed_hash(hashed: str | None) -> None:
    assert FAST.verify(SECRET, hashed) is False


def test_verify_returns_false_for_empty_or_overlong_password() -> None:
    hashed = FAST.hash(SECRET)
    assert FAST.verify("", hashed) is False
    assert FAST.verify("x" * (MAX_PASSWORD_BYTES + 1), hashed) is False


def test_dummy_hash_table_entries_match_their_cost() -> None:
    for rounds, hashed in bcrypt_hasher._DUMMY_HASHES.items():
        assert hashed.startswith(f"$2b${rounds:02d}$")
        assert BcryptHasher(rounds=rounds).verify("anything", hashed) is False


def test_verify_dummy_pays_one_bcrypt_check_at_the_same_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[bytes, bytes]] = []
    real = bcrypt.checkpw

    def _spy(password: bytes, hashed: bytes) -> bool:
        seen.append((password, hashed))
        return real(password, hashed)

    monkeypatch.setattr(bcrypt, "checkpw", _spy)

    FAST.verify_dummy("whatever")

    assert len(seen) == 1
    assert seen[0][0] == b"whatever"
    assert seen[0][1].startswith(b"$2b$04$")


def test_verify_dummy_computes_for_cost_outside_table() -> None:
    BcryptHasher(rounds=5).verify_dummy("whatever")  # must not raise


def test_needs_rehash_compares_stored_cost_with_configured_cost() -> None:
    cost5 = BcryptHasher(rounds=5)
    assert cost5.needs_rehash(FAST.hash(SECRET)) is True
    assert cost5.needs_rehash(cost5.hash(SECRET)) is False
    assert cost5.needs_rehash(None) is False
    assert cost5.needs_rehash("not-a-bcrypt-hash") is False
