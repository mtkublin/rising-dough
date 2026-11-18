"""Delete plaintext Litestream objects from the prod replica (T-D56, ADR-0078 §3, ADR-0112).

Litestream 0.3.14 does not start a new generation when `age.recipients` is
enabled: the running generation continues and only NEW snapshots and WAL
segments are age ciphertext. So a generation can mix plaintext and encrypted
objects, and "plaintext generation" is not a usable test. This script classifies
every object by its first bytes instead:

  age-encryption.org/v1   -> encrypted (age header)
  04 22 4D 18             -> plaintext (LZ4 frame magic, the pre-encryption format)
  anything else           -> unknown: the run is refused

Object layout (litestream 0.3.x, names are unchanged by encryption):
  db/generations/<16 hex>/snapshots/<8 hex index>.snapshot.lz4
  db/generations/<16 hex>/wal/<8 hex index>_<8 hex offset>.wal.lz4

A plaintext object is deletable only when a restore can never need it:
  * its generation has an encrypted snapshot and the object's index is STRICTLY
    below that snapshot's index (restore starts at the newest snapshot and
    replays WAL from that index on), or
  * its generation has no encrypted object and every object in it is older than
    the newest encrypted snapshot (a superseded old generation).
Anything else that is still plaintext is a blocker: the run is refused and nothing
is deleted (typically: wait for the next daily snapshot).

Gates (all must hold, otherwise exit 2 and nothing is deleted):
  1. at least one encrypted snapshot exists;
  2. no object of unknown format;
  3. no blocker (see above);
  4. restore-log.md holds a green entry (`Result: pass`, `integrity_check: ok`)
     dated on or after the day of the first encrypted snapshot of the newest
     encrypted generation.
`--apply` deletes; without it the run is a dry run. The bucket is versioned, so a
delete leaves a noncurrent version that expires with the bucket lifecycle rule
(T-D57), which is the undo window.
"""

# ruff: noqa: S603  # fixed aws argv, no shell
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess  # nosec B404
import sys
import tempfile
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

AGE_MAGIC = b"age-encryption.org/v1"
LZ4_MAGIC = bytes.fromhex("04224d18")
HEAD_BYTES = 32
MAX_OBJECTS = 200_000
DELETE_BATCH = 500
EXIT_REFUSED = 2

KEY_RE = re.compile(
    r"^(?P<prefix>.+)/generations/(?P<gen>[0-9a-f]{16})/"
    r"(?:snapshots/(?P<sidx>[0-9a-f]{8})\.snapshot\.lz4"
    r"|wal/(?P<widx>[0-9a-f]{8})_(?P<off>[0-9a-f]{8})\.wal\.lz4)$"
)
ENTRY_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
RESULT_RE = re.compile(r"^\s*-\s*\*\*Result\*\*:\s*(\S+)", re.MULTILINE | re.IGNORECASE)
INTEGRITY_RE = re.compile(r"^\s*-\s*\*\*integrity_check\*\*:\s*(\S+)", re.MULTILINE | re.IGNORECASE)

PLAIN = "plaintext"
ENCRYPTED = "encrypted"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class S3Object:
    key: str
    last_modified: datetime


@dataclass(frozen=True)
class Parsed:
    obj: S3Object
    generation: str
    kind: str  # "snapshot" | "wal"
    index: int


@dataclass(frozen=True)
class Plan:
    delete: tuple[str, ...]
    keep_plain: int
    encrypted: int
    ignored: tuple[str, ...]
    blockers: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def refused(self) -> bool:
        return bool(self.blockers or self.errors)


class S3Client(Protocol):
    def list_objects(self, prefix: str) -> list[S3Object]: ...
    def read_head(self, key: str) -> bytes: ...
    def delete(self, keys: Sequence[str]) -> None: ...


def classify_header(head: bytes) -> str:
    if head.startswith(AGE_MAGIC):
        return ENCRYPTED
    if head.startswith(LZ4_MAGIC):
        return PLAIN
    return UNKNOWN


def parse_key(obj: S3Object) -> Parsed | None:
    match = KEY_RE.fullmatch(obj.key)
    if match is None:
        return None
    if match["sidx"] is not None:
        return Parsed(obj, match["gen"], "snapshot", int(match["sidx"], 16))
    return Parsed(obj, match["gen"], "wal", int(match["widx"], 16))


def restore_log_green_dates(text: str) -> list[date]:
    """Dates of entries with `Result: pass` and `integrity_check: ok`."""
    heads = list(ENTRY_RE.finditer(text))
    green: list[date] = []
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[head.end() : end]
        result, integrity = RESULT_RE.search(body), INTEGRITY_RE.search(body)
        if result and integrity and result[1].lower() == "pass" and integrity[1].lower() == "ok":
            green.append(date.fromisoformat(head[1]))
    return green


def _encrypted_snapshots(items: Iterable[Parsed], kinds: dict[str, str]) -> list[Parsed]:
    return [p for p in items if p.kind == "snapshot" and kinds[p.obj.key] == ENCRYPTED]


def plan_cleanup(objects: Sequence[S3Object], kinds: dict[str, str], restore_log: str) -> Plan:
    """Pure decision function. `kinds` maps every recognised key to a classification."""
    parsed = [p for o in objects if (p := parse_key(o)) is not None]
    ignored = tuple(o.key for o in objects if parse_key(o) is None)
    errors: list[str] = [
        f"unknown object format (neither age nor LZ4): {p.obj.key}"
        for p in parsed
        if kinds[p.obj.key] == UNKNOWN
    ]
    enc_snaps = _encrypted_snapshots(parsed, kinds)
    encrypted_n = sum(1 for p in parsed if kinds[p.obj.key] == ENCRYPTED)
    if not enc_snaps:
        errors.append("no encrypted snapshot in the replica: nothing proves a restore can use it")
        return Plan((), 0, encrypted_n, ignored, (), tuple(errors))

    newest = max(enc_snaps, key=lambda p: p.obj.last_modified)
    first_in_gen = min(
        (p for p in enc_snaps if p.generation == newest.generation),
        key=lambda p: p.obj.last_modified,
    )
    since = first_in_gen.obj.last_modified.astimezone(UTC).date()
    if not any(d >= since for d in restore_log_green_dates(restore_log)):
        errors.append(
            "restore-log.md has no green entry (Result: pass, integrity_check: ok) dated on or "
            f"after {since.isoformat()}, the day of the first encrypted snapshot of generation "
            f"{newest.generation}"
        )

    max_enc_snap_index: dict[str, int] = {}
    for p in enc_snaps:
        max_enc_snap_index[p.generation] = max(max_enc_snap_index.get(p.generation, -1), p.index)
    gens_with_encrypted = {p.generation for p in parsed if kinds[p.obj.key] == ENCRYPTED}

    delete: list[str] = []
    blockers: list[str] = []
    for p in sorted(parsed, key=lambda q: q.obj.key):
        if kinds[p.obj.key] != PLAIN:
            continue
        gen_snap_index = max_enc_snap_index.get(p.generation)
        if gen_snap_index is not None:
            if p.index < gen_snap_index:
                delete.append(p.obj.key)
            else:
                blockers.append(
                    f"{p.obj.key}: plaintext at index {p.index} >= newest encrypted snapshot "
                    f"index {gen_snap_index} of its generation; wait for the next snapshot"
                )
        elif p.generation in gens_with_encrypted:
            blockers.append(f"{p.obj.key}: generation has encrypted WAL but no encrypted snapshot")
        elif p.obj.last_modified < newest.obj.last_modified:
            delete.append(p.obj.key)
        else:
            blockers.append(
                f"{p.obj.key}: plaintext generation {p.generation} is newer than the newest "
                "encrypted snapshot"
            )
    kept = sum(1 for p in parsed if kinds[p.obj.key] == PLAIN) - len(delete)
    return Plan(tuple(delete), kept, encrypted_n, ignored, tuple(blockers), tuple(errors))


def classify_all(client: S3Client, objects: Sequence[S3Object], workers: int = 8) -> dict[str, str]:
    keys = [o.key for o in objects if parse_key(o) is not None]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        heads = list(pool.map(client.read_head, keys))
    return {k: classify_header(h) for k, h in zip(keys, heads, strict=True)}


def render(plan: Plan, apply: bool) -> str:
    mode = "APPLY" if apply else "DRY RUN"
    lines = [
        f"### Litestream plaintext cleanup ({mode})",
        "",
        f"- encrypted objects: {plan.encrypted}",
        f"- plaintext objects to delete: {len(plan.delete)}",
        f"- plaintext objects kept: {plan.keep_plain}",
        f"- unrecognised keys (never touched): {len(plan.ignored)}",
    ]
    for label, items in (("REFUSED (error)", plan.errors), ("REFUSED (blocker)", plan.blockers)):
        lines.extend(f"- **{label}**: {item}" for item in items[:50])
    if plan.delete:
        lines += ["", "Objects to delete (first 200):", "", "```"]
        lines += [*plan.delete[:200], "```"]
    return "\n".join(lines)


def run(
    client: S3Client,
    prefix: str,
    restore_log: str,
    apply: bool,
    out: Callable[[str], None] = print,
) -> int:
    objects = client.list_objects(prefix)
    if len(objects) > MAX_OBJECTS:
        out(f"REFUSED: {len(objects)} objects exceeds the safety cap {MAX_OBJECTS}")
        return EXIT_REFUSED
    plan = plan_cleanup(objects, classify_all(client, objects), restore_log)
    out(render(plan, apply))
    if plan.refused:
        return EXIT_REFUSED
    if apply and plan.delete:
        for i in range(0, len(plan.delete), DELETE_BATCH):
            client.delete(plan.delete[i : i + DELETE_BATCH])
        out(f"\nDeleted {len(plan.delete)} plaintext objects.")
    elif not apply:
        out("\nDry run: nothing deleted. Re-dispatch with dry_run=false to apply.")
    return 0


class AwsCliClient:
    """S3 access through the `aws` CLI (preinstalled on GitHub runners)."""

    def __init__(self, bucket: str, endpoint: str, region: str) -> None:
        self._bucket = bucket
        self._base = ["aws", "--endpoint-url", endpoint, "--region", region]

    def _s3api(self, *args: str) -> str:
        proc = subprocess.run(  # nosec B603 B607
            [*self._base, "s3api", *args], check=True, capture_output=True, text=True
        )
        return proc.stdout

    def list_objects(self, prefix: str) -> list[S3Object]:
        out = self._s3api(
            "list-objects-v2", "--bucket", self._bucket, "--prefix", prefix, "--output", "json"
        )
        contents = (json.loads(out) if out.strip() else None) or {}
        return [
            S3Object(c["Key"], datetime.fromisoformat(c["LastModified"]))
            for c in contents.get("Contents", [])
        ]

    def read_head(self, key: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "head"
            self._s3api(
                "get-object", "--bucket", self._bucket, "--key", key,
                "--range", f"bytes=0-{HEAD_BYTES - 1}", str(target),
            )  # fmt: skip
            return target.read_bytes()

    def delete(self, keys: Sequence[str]) -> None:
        payload = json.dumps({"Objects": [{"Key": k} for k in keys], "Quiet": True})
        out = self._s3api("delete-objects", "--bucket", self._bucket, "--delete", payload)
        errors = (json.loads(out) if out.strip() else {}).get("Errors", [])
        if errors:
            raise RuntimeError(f"delete-objects reported {len(errors)} errors: {errors[:3]}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else "")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--prefix", default="db/generations/")
    parser.add_argument("--restore-log", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="delete; default is a dry run")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not os.environ.get("AWS_ACCESS_KEY_ID") or not os.environ.get("AWS_SECRET_ACCESS_KEY"):
        print("::error::AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY are not set", file=sys.stderr)
        return 1
    client = AwsCliClient(args.bucket, args.endpoint, args.region)
    return run(client, args.prefix, args.restore_log.read_text(), args.apply)


if __name__ == "__main__":
    sys.exit(main())
