# ADR-0114: Litestream Replicate Config Carries the Age Identity; One Forced New Generation

- **Status**: Accepted
- **Date**: 2026-11-18
- **Amends**: ADR-0078 §3 (age replica encryption)
- **Relates to**: ADR-0034 §3, ADR-0111, ADR-0112
- **Task**: T-D136

## Context

ADR-0078 §3 configured `litestream replicate` with `age.recipients` only. On every start Litestream 0.3.14 (`Replica.Sync` then `calcPos`) reads the newest WAL segment of the current generation and decrypts it only when `age.identities` is set. With a recipient-only config and an age-encrypted last segment, the start fails with `cannot determine replica position` and replication stalls silently (the monitor loop logs and retries). Prod has run recipient-only since `v3.0.1`. Adding identities alone is not enough: Litestream 0.3.14 does not start a new generation when encryption is switched on, so the current generation holds plaintext segments followed by ciphertext, and decrypting a plaintext last segment fails too.

## Decision

1. The replicate config carries both `recipients` and `identities: [$LITESTREAM_AGE_IDENTITY]` (prod, drill, prod-sim). The identity comes from the existing `/etc/budget-planner/litestream-age.key` (0600, written by the host agent), mounted read-only into the litestream container.
2. The litestream service uses a small entrypoint, `terraform/cloud-init/compose/litestream-entrypoint.sh`, delivered as a host-agent managed file. It exports the identity and, if the marker `/data/.litestream-age-generation` is absent, removes Litestream's local meta dir `/data/.budget.db-litestream` and writes the marker. With no generation on record, Litestream opens a new generation on start (fresh snapshot), so every object the running replicator ever has to read back is ciphertext. The SQLite database and its WAL are never touched.
3. The marker makes the reset happen once per host. Fresh hosts (drill, restored prod) have no meta dir, so the reset is a no-op there.
4. Old plaintext or mixed generations stay in the bucket until ADR-0112's cleanup removes them; restores use the newest generation, which is fully ciphertext.

## Consequences

- One new generation in the prod bucket at the first converge after release; one extra full snapshot upload.
- A restart of the litestream container is safe in every state afterwards.
- An identity change restarts litestream (the key file is a restart trigger).
- Rejected: a wrapper that reacts to the `cannot determine replica position` log line (fragile log scraping, stalls until detected); a re-snapshot via `litestream` CLI (0.3.14 has no command to force a generation).
