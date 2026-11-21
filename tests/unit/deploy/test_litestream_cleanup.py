"""Unit tests for scripts/ci/litestream_cleanup.py (T-D56, ADR-0112). No network, no aws CLI."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ci" / "litestream_cleanup.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("litestream_cleanup", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


lc = _load()

GEN_A = "aaaaaaaaaaaaaaaa"
GEN_B = "bbbbbbbbbbbbbbbb"
T0 = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
AGE = b"age-encryption.org/v1\n-> X25519 abc"
LZ4 = bytes.fromhex("04224d18") + b"\x00" * 20
GREEN = "## 2026-11-20\n- **integrity_check**: ok\n- **Result**: pass\n"


def snap(gen: str, idx: int, day: int) -> str:
    return f"db/generations/{gen}/snapshots/{idx:08x}.snapshot.lz4"


def wal(gen: str, idx: int, off: int = 0) -> str:
    return f"db/generations/{gen}/wal/{idx:08x}_{off:08x}.wal.lz4"


class FakeClient:
    def __init__(self, heads: dict[str, bytes], when: dict[str, datetime]) -> None:
        self.heads, self.when = heads, when
        self.deleted: list[str] = []

    def list_objects(self, prefix: str) -> list[Any]:
        return [lc.S3Object(k, self.when[k]) for k in self.heads if k.startswith(prefix)]

    def read_head(self, key: str) -> bytes:
        return self.heads[key]

    def delete(self, keys: Sequence[str]) -> None:
        self.deleted.extend(keys)


def mixed_generation() -> FakeClient:
    """GEN_A: plaintext snap 1, wal 1,2; encrypted snap 3 (day 2) and wal 3."""
    entries = {
        snap(GEN_A, 1, 0): (LZ4, 0),
        wal(GEN_A, 1): (LZ4, 0),
        wal(GEN_A, 2): (LZ4, 1),
        snap(GEN_A, 3, 2): (AGE, 2),
        wal(GEN_A, 3): (AGE, 2),
    }
    return FakeClient(
        {k: v[0] for k, v in entries.items()},
        {k: T0 + timedelta(days=v[1]) for k, v in entries.items()},
    )


def test_classify_header() -> None:
    assert lc.classify_header(AGE) == lc.ENCRYPTED
    assert lc.classify_header(LZ4) == lc.PLAIN
    assert lc.classify_header(b"garbage") == lc.UNKNOWN
    assert lc.classify_header(b"") == lc.UNKNOWN


def test_parse_key() -> None:
    p = lc.parse_key(lc.S3Object(wal(GEN_A, 255, 4), T0))
    assert (p.generation, p.kind, p.index) == (GEN_A, "wal", 255)
    assert lc.parse_key(lc.S3Object("db/other", T0)) is None
    assert lc.parse_key(lc.S3Object("db/generations/xyz/wal/zz", T0)) is None


def test_restore_log_green_dates() -> None:
    log = (
        "## 2026-11-22\n- **integrity_check**: ok\n- **Result**: fail\n\n"
        "## 2026-11-21\n- **integrity_check**: failed-x\n- **Result**: pass\n\n"
        "## 2026-11-20\n- **integrity_check**: ok\n- **Result**: pass\n"
    )
    assert [d.isoformat() for d in lc.restore_log_green_dates(log)] == ["2026-11-20"]
    assert lc.restore_log_green_dates("no entries") == []


def test_mixed_generation_deletes_only_plaintext_below_encrypted_snapshot() -> None:
    client = mixed_generation()
    assert lc.run(client, "db/", GREEN, apply=True, out=lambda _: None) == 0
    assert sorted(client.deleted) == sorted([snap(GEN_A, 1, 0), wal(GEN_A, 1), wal(GEN_A, 2)])


def test_dry_run_deletes_nothing() -> None:
    client = mixed_generation()
    assert lc.run(client, "db/", GREEN, apply=False, out=lambda _: None) == 0
    assert client.deleted == []


def test_refuses_without_encrypted_snapshot() -> None:
    client = FakeClient({wal(GEN_A, 1): LZ4}, {wal(GEN_A, 1): T0})
    assert lc.run(client, "db/", GREEN, apply=True, out=lambda _: None) == lc.EXIT_REFUSED
    assert client.deleted == []


def test_refuses_without_green_restore_log_after_first_encrypted_snapshot() -> None:
    for log in ("", "## 2026-11-11\n- **integrity_check**: ok\n- **Result**: pass\n"):
        client = mixed_generation()  # first encrypted snapshot is on 2026-11-12
        assert lc.run(client, "db/", log, apply=True, out=lambda _: None) == lc.EXIT_REFUSED
        assert client.deleted == []


def test_restore_log_same_day_as_first_encrypted_snapshot_is_enough() -> None:
    log = "## 2026-11-12\n- **integrity_check**: ok\n- **Result**: pass\n"
    assert lc.run(mixed_generation(), "db/", log, apply=False, out=lambda _: None) == 0


def test_refuses_on_unknown_format() -> None:
    client = mixed_generation()
    client.heads[wal(GEN_A, 2)] = b"\x00\x01 not lz4 not age"
    assert lc.run(client, "db/", GREEN, apply=True, out=lambda _: None) == lc.EXIT_REFUSED
    assert client.deleted == []


def test_refuses_plaintext_at_or_above_encrypted_snapshot_index() -> None:
    client = mixed_generation()
    client.heads[wal(GEN_A, 3, 8)] = LZ4  # plaintext at the snapshot index
    client.when[wal(GEN_A, 3, 8)] = T0
    assert lc.run(client, "db/", GREEN, apply=True, out=lambda _: None) == lc.EXIT_REFUSED
    assert client.deleted == []


def test_old_plaintext_generation_deleted_when_older_than_newest_encrypted_snapshot() -> None:
    client = mixed_generation()
    for key in (snap(GEN_B, 1, 0), wal(GEN_B, 1)):
        client.heads[key] = LZ4
        client.when[key] = T0 - timedelta(days=5)
    assert lc.run(client, "db/", GREEN, apply=True, out=lambda _: None) == 0
    assert snap(GEN_B, 1, 0) in client.deleted and wal(GEN_B, 1) in client.deleted
    assert snap(GEN_A, 3, 2) not in client.deleted and wal(GEN_A, 3) not in client.deleted


def test_newer_plaintext_generation_blocks() -> None:
    client = mixed_generation()
    client.heads[snap(GEN_B, 1, 0)] = LZ4
    client.when[snap(GEN_B, 1, 0)] = T0 + timedelta(days=9)
    assert lc.run(client, "db/", GREEN, apply=True, out=lambda _: None) == lc.EXIT_REFUSED
    assert client.deleted == []


def test_unrecognised_keys_are_never_deleted() -> None:
    client = mixed_generation()
    client.heads["db/generations/notes.txt"] = b"x"
    client.when["db/generations/notes.txt"] = T0
    assert lc.run(client, "db/", GREEN, apply=True, out=lambda _: None) == 0
    assert "db/generations/notes.txt" not in client.deleted


def test_delete_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lc, "DELETE_BATCH", 2)
    batches: list[int] = []
    client = mixed_generation()
    client.delete = lambda keys: batches.append(len(keys))  # type: ignore[method-assign]
    assert lc.run(client, "db/", GREEN, apply=True, out=lambda _: None) == 0
    assert batches == [2, 1]


def test_workflow_is_dispatch_only_prod_gated_dry_run_default() -> None:
    path = ROOT / ".github" / "workflows" / "litestream-plaintext-cleanup.yml"
    wf = yaml.safe_load(path.read_text())
    assert list(wf[True]) == ["workflow_dispatch"]  # YAML parses `on` as True
    assert wf[True]["workflow_dispatch"]["inputs"]["dry_run"]["default"] is True
    job = wf["jobs"]["cleanup"]
    assert job["environment"] == "prod"
    assert wf["permissions"] == {"contents": "read"}
    for step in job["steps"]:
        uses = step.get("uses")
        if uses:
            assert len(uses.split("@")[1].split()[0]) == 40
