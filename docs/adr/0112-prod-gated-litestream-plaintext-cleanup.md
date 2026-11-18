# ADR-0112: Prod-Gated Cleanup of Plaintext Litestream Objects

- **Status**: Accepted
- **Date**: 2026-11-18
- **Relates to**: ADR-0078 §3 (age replica encryption), ADR-0099 (release and environment policy), ADR-0100 (credential split), ADR-0034 §5 (restore drill)
- **Task**: T-D56

## Context

ADR-0078 §3 says to delete the plaintext generations after the encrypted replica is proven by a restore drill, using "the bucket tooling". Two facts make that unsafe to do by hand:

- Litestream 0.3.14 does not start a new generation when `age.recipients` is enabled. The running generation continues, so one generation holds plaintext objects (before the restart) and age ciphertext (after it). Deleting by generation prefix would either keep plaintext or destroy the live generation.
- The deletion is irreversible once the noncurrent-version window (7 d) has passed, and it must never happen before a restore with the identity has been proven.

CLAUDE.md allows prod changes only through GitHub Actions with approval (ADR-0099); a laptop `aws s3 rm` against the prod bucket is exactly what that policy forbids.

## Decision

1. A dispatch-only workflow, `litestream-plaintext-cleanup.yml`, runs in the `prod` environment (required reviewer = approval click), from `main` only, with input `dry_run` defaulting to `true`.
2. It uses the prod environment's existing `APP_SCW_ACCESS_KEY` / `APP_SCW_SECRET_KEY` (the replication key: list/get/put/delete on the prod bucket only). No new credential, no wider access.
3. Selection is per object, not per generation (`scripts/ci/litestream_cleanup.py`, unit-tested). Each replica object is classified by its first 32 bytes: `age-encryption.org/v1` is encrypted, the LZ4 frame magic `04 22 4D 18` is plaintext, anything else is refused. A plaintext object is deleted only if its index is strictly below the newest encrypted snapshot of its generation (a restore starts there), or it belongs to a wholly plaintext generation older than the newest encrypted snapshot.
4. The run refuses (exit 2, nothing deleted, in dry run too) unless: an encrypted snapshot exists; no object has an unknown format; no plaintext object is still needed by a restore; and `docs/plans/v3/runbooks/restore-log.md` has a green entry (`Result: pass`, `integrity_check: ok`) dated on or after the first encrypted snapshot of the newest encrypted generation.
5. Deletes are plain `DeleteObjects` without version ids. The bucket is versioned, so the plaintext copies remain as noncurrent versions until the lifecycle rule expires them (T-D57: 7 d). That is the undo window and the point at which no plaintext copy is left.

## Consequences

- The cut-over is: restore drill green, dispatch dry run, review, dispatch with `dry_run=false`, approve (runbook `restore.md`).
- The restore-log gate is date-based (entries carry a date, not a time), so a drill on the same day as the first encrypted snapshot counts.
- The script needs the `aws` CLI (preinstalled on `ubuntu-latest`) and checksum settings that Scaleway accepts (`when_required`).
- Plaintext copies persist for up to 7 days after the delete, inside the 37-day ceiling of ADR-0078 §4.

## Note 2026-11-18: no read-only key for the dry run; T-D56 closes without a delete run

A read-only S3 key for the cleanup dry run was considered and rejected by the user. The dry run is already protected by `--apply` (off by default) and the refusal gate, and the dry run (run 44328479375) found 0 plaintext objects in the prod bucket (the one-time new generation of ADR-0114 left only ciphertext in use, and the older generations hold nothing that is still plaintext and needed). So T-D56 closes without a delete run; the workflow and script stay for any future plaintext finding.
