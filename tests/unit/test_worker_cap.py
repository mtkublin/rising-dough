"""`-n auto` is capped inside linked git worktrees (T-Q327, ADR-0150 §6)."""

from __future__ import annotations

from pathlib import Path

from tests.worker_cap import WORKTREE_AUTO_WORKERS, auto_workers


def test_linked_worktree_caps_auto_at_two(tmp_path: Path) -> None:
    (tmp_path / ".git").write_text("gitdir: /repo/.git/worktrees/item\n")
    assert WORKTREE_AUTO_WORKERS == 2
    assert auto_workers(tmp_path) == 2


def test_main_checkout_keeps_the_xdist_default(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    assert auto_workers(tmp_path) is None


def test_no_git_metadata_keeps_the_xdist_default(tmp_path: Path) -> None:
    assert auto_workers(tmp_path) is None
