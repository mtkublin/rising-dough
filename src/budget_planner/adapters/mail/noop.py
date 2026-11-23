"""No-op ``MailSender``: the only production adapter until T-UR18 is go (ADR-0134 section 1).

Logs one fixed event. The recipient, subject and body (which carries the invite
link and token) are never logged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from budget_planner.domain.ports import MailMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class NoopMailSender:
    """Drops every message."""

    def send(self, message: MailMessage) -> None:
        logger.info("mail.noop: dropped %s (no provider configured)", type(message).__name__)
