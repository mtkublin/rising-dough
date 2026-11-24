"""xdist worker cap for orchestrated item agents (ADR-0150 §6, T-Q327).

Parallel item agents each run in a linked git worktree, where ``.git`` is a
file pointing at the main repository. There ``-n auto`` resolves to
``WORKTREE_AUTO_WORKERS``, so a stray ``-n auto`` cannot start one worker per
core per agent. The main checkout and CI return ``None`` and keep xdist's own
default. An explicit ``-n <n>`` or ``PYTEST_WORKERS`` never reaches this.
"""

from __future__ import annotations

from pathlib import Path

WORKTREE_AUTO_WORKERS = 2


def auto_workers(root: Path) -> int | None:
    """Workers for ``-n auto`` under ``root``: the cap in a linked worktree, else ``None``."""
    return WORKTREE_AUTO_WORKERS if (root / ".git").is_file() else None
