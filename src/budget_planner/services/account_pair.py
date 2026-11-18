"""Source / destination account rule (T-D153).

``planned_transactions`` and ``transactions`` carry
``CHECK (account_id <> dest_account_id OR dest_account_id IS NULL)``. Routers
call this before writing so a violation is a validation error, not a 500.
"""

from __future__ import annotations

SAME_ACCOUNT_MESSAGE = "destination must differ from the source account"


def validate_distinct_accounts(account_id: int, dest_account_id: int | None) -> str | None:
    """Return an error message when source and destination are the same account."""
    if dest_account_id is not None and dest_account_id == account_id:
        return SAME_ACCOUNT_MESSAGE
    return None
