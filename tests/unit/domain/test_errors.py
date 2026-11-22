"""Domain error string forms (the messages the web layer shows)."""

from __future__ import annotations

from budget_planner.domain.errors import ConflictError, NotFoundError, ServiceError, ValidationError


def test_validation_error_joins_fields() -> None:
    assert str(ValidationError(fields={"a": "x", "b": "y"})) == "a: x; b: y"


def test_validation_error_without_fields_has_default_text() -> None:
    assert str(ValidationError()) == "validation error"


def test_not_found_error_names_entity_and_id() -> None:
    assert str(NotFoundError(entity="account", entity_id=7)) == "account 7 not found"


def test_conflict_error_str_is_message() -> None:
    err = ConflictError("duplicate name")
    assert str(err) == "duplicate name"
    assert err.message == "duplicate name"


def test_service_error_default_and_custom_message() -> None:
    assert str(ServiceError()) == "something went wrong"
    assert str(ServiceError("boom")) == "boom"
