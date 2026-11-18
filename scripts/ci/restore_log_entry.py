"""Build a restore-log entry from restore-drill facts (T-D41, runbooks/restore-log.md).

The restore-drill workflow cannot commit to protected `main`, so every run writes the
entry to the job summary and posts it as a comment on the `restore-log` issue.

Inputs are plain strings from workflow step outputs and the captured `restore-from-prod`
output. Every value is validated against a strict pattern before it is rendered, so the
entry never carries free text from the drill host (no secrets, no injected markdown). The
entry keeps the format `scripts/ci/litestream_cleanup.py` parses: a `## YYYY-MM-DD`
heading, `- **Result**: pass` and `- **integrity_check**: ok`.

Stdlib only. Prod row counts cannot be read from CI and are recorded as not queried.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

UNKNOWN = "unknown"
PROD_NOT_QUERIED = "n/a (prod not queried)"

_GENERATION = r"[0-9a-f]{16}"
SNAPSHOT_RE = re.compile(rf"restoring snapshot ({_GENERATION})/([0-9a-f]{{1,8}})")
WAL_RANGE_RE = re.compile(
    rf"restoring wal files:?\s+generation=({_GENERATION})\s+index=\[([0-9a-f]+),\s*([0-9a-f]+)\]"
)
SOURCE_RE = re.compile(r"restoring from (s3://[A-Za-z0-9._\-/]+)")
AUDIT_RE = re.compile(r"^(\d+)\|(\d*)\|([0-9TZ:.\-]*)$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")
REF_RE = re.compile(r"^[A-Za-z0-9._:@/\-]{1,200}$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
TRIGGERS = {"schedule": "scheduled-monthly", "workflow_dispatch": "manual-ad-hoc"}
RESULTS = ("pass", "fail")


@dataclass(frozen=True)
class RestoreOutput:
    """What the restore helper reported about the replica it restored from."""

    source: str
    generation: str
    snapshot_index: int | None
    wal_min: int | None
    wal_max: int | None


@dataclass(frozen=True)
class AuditStats:
    count: int
    max_id: int | None
    max_changed_at: str


@dataclass(frozen=True)
class Facts:
    result: str
    trigger: str
    run_url: str
    image_ref: str
    restore: RestoreOutput
    audit: AuditStats | None
    integrity: str
    ready: str
    extra_copies: str
    started_at: datetime | None
    ready_at: datetime | None
    restored_at: str


def parse_restore_output(text: str) -> RestoreOutput:
    """Read source, generation and index range from the litestream restore log."""
    source = SOURCE_RE.search(text)
    snap = SNAPSHOT_RE.search(text)
    wal = WAL_RANGE_RE.search(text)
    generation = (snap and snap[1]) or (wal and wal[1]) or UNKNOWN
    return RestoreOutput(
        source=source[1] if source else UNKNOWN,
        generation=generation,
        snapshot_index=int(snap[2], 16) if snap else None,
        wal_min=int(wal[2], 16) if wal else None,
        wal_max=int(wal[3], 16) if wal else None,
    )


def parse_audit(raw: str) -> AuditStats | None:
    """Parse `count|max_id|max_changed_at` (sqlite3 -separator '|'); None when malformed."""
    match = AUDIT_RE.match(raw.strip())
    if match is None:
        return None
    return AuditStats(int(match[1]), int(match[2]) if match[2] else None, match[3])


def parse_iso(value: str) -> datetime | None:
    if not ISO_RE.match(value.strip()):
        return None
    return datetime.strptime(value.strip(), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def format_duration(start: datetime | None, end: datetime | None) -> str:
    if start is None or end is None or end < start:
        return "n/a"
    seconds = int((end - start).total_seconds())
    return f"{seconds // 60}m{seconds % 60:02d}s"


def _token(value: str, fallback: str = UNKNOWN) -> str:
    cleaned = value.strip()
    return cleaned if TOKEN_RE.match(cleaned) else fallback


def _wal_text(restore: RestoreOutput) -> str:
    if restore.wal_min is None or restore.wal_max is None:
        return "WAL range unknown"
    return f"WAL index {restore.wal_min}..{restore.wal_max}"


def _source_line(facts: Facts) -> str:
    restore = facts.restore
    snapshot = "unknown" if restore.snapshot_index is None else str(restore.snapshot_index)
    restored_at = facts.restored_at if ISO_RE.match(facts.restored_at) else UNKNOWN
    return (
        f"{restore.source}, generation {restore.generation}, snapshot index {snapshot}, "
        f"{_wal_text(restore)}, restored at {restored_at}"
    )


def _audit_line(audit: AuditStats | None) -> str:
    if audit is None:
        return "not collected"
    max_id = "none" if audit.max_id is None else str(audit.max_id)
    return f"{audit.count}, max_id={max_id}, max_changed_at={audit.max_changed_at or 'none'}"


def build_entry(facts: Facts) -> str:
    """Render the entry in the restore-log template format."""
    result = facts.result if facts.result in RESULTS else "fail"
    day = (facts.ready_at or facts.started_at or datetime.now(UTC)).date().isoformat()
    integrity = _token(facts.integrity, "not-run")
    trigger = TRIGGERS.get(facts.trigger, "manual-ad-hoc")
    image_ref = facts.image_ref if REF_RE.match(facts.image_ref) else UNKNOWN
    notes = (
        f"workflow run {facts.run_url}; app image {image_ref}; "
        f"/ready: {facts.ready or 'not-run'}; extra DB copies (T-D57): "
        f"{facts.extra_copies or 'not-run'}."
    )
    lines = [
        f"## {day}",
        "- **Operator**: system-restore-drill",
        "- **Env**: drill-scratch-vm",
        f"- **Trigger**: {trigger}",
        f"- **Duration**: {format_duration(facts.started_at, facts.ready_at)}"
        " (run start -> green /ready)",
        f"- **Source**: {_source_line(facts)}",
        f"- **Audit rows (prod)**: {PROD_NOT_QUERIED}",
        f"- **Audit rows (restored)**: {_audit_line(facts.audit)}",
        f"- **integrity_check**: {integrity}",
        "- **Recovery point**: latest (newest WAL segment in the replica at restore time)",
        f"- **Result**: {result}",
        f"- **Notes**: {notes}",
    ]
    return "\n".join(lines) + "\n"


def _facts_from_args(args: argparse.Namespace) -> Facts:
    text = Path(args.restore_output).read_text(errors="replace") if args.restore_output else ""
    return Facts(
        result=args.result,
        trigger=args.trigger,
        run_url=args.run_url,
        image_ref=args.image_ref,
        restore=parse_restore_output(text),
        audit=parse_audit(args.audit),
        integrity=args.integrity,
        ready=_token(args.ready, "not-run"),
        extra_copies=_token(args.extra_copies, "not-run"),
        started_at=parse_iso(args.started_at),
        ready_at=parse_iso(args.ready_at),
        restored_at=args.restored_at,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, choices=RESULTS)
    parser.add_argument("--trigger", default="workflow_dispatch")
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--image-ref", default="")
    parser.add_argument("--restore-output", default="")
    parser.add_argument("--audit", default="")
    parser.add_argument("--integrity", default="")
    parser.add_argument("--ready", default="")
    parser.add_argument("--extra-copies", default="")
    parser.add_argument("--started-at", default="")
    parser.add_argument("--ready-at", default="")
    parser.add_argument("--restored-at", default="")
    sys.stdout.write(build_entry(_facts_from_args(parser.parse_args(argv))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
