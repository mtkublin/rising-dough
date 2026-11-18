# ADR-0115: A Drill VM Is Exclusive; Every Drill Workflow Starts With a Drill Lock

- **Status**: Accepted
- **Date**: 2026-11-18
- **Relates to**: ADR-0099 (release and environment policy, drill concurrency), ADR-0101 (tailnet-only drill), ADR-0092 (separate drill project)
- **Task**: T-D138

## Context

All drill workflows share the concurrency group `drill`. That serialises runs, not VMs:

- A kept explore drill finishes its run after apply and smoke, but its VM lives on until its `expires-at` tag. The group is then free, so a gate or `restore-drill.yml` can start, `-replace` that VM (same Terraform state) and destroy it, silently.
- A concurrency group holds one pending run; dispatching another cancels the older pending run without notice.

## Decision

1. A drill VM is exclusive. No drill workflow may create or replace it while a drill VM exists or another drill-group run is active.
2. `drill.yml`, `restore-drill.yml`, `drill-destroy.yml` and `drill-sweeper.yml` start with job `drill-lock`; every other job depends on it. It runs `scripts/ci/drill_lock.py` and fails the run with `::error::` naming the holder. Checks: (a) another drill-group run (`drill`, `restore-drill`, `drill-destroy`, `drill-sweeper`, `rollback` with env drill) is active, via the GitHub API with `actions: read`; (b) a server named `budget-planner-drill*` exists in the Scaleway drill project (ground truth; reports `expires-at` and creation time); (c) an online `tag:drill` node exists in the tailnet (cross-check, read-only, `TS_CLEANUP_*`).
3. The lock never destroys anything. An expired VM the sweeper has not yet removed also fails ("run drill-destroy.yml first").
4. `drill-destroy.yml` and `drill-sweeper.yml` check (a) only, since they clear (b)/(c). `rollback.yml env=drill` is unchanged (it needs a VM) but gets `run-name: rollback (<env>)` so the lock can ignore prod rollbacks.
5. Input `force` (default false, `drill.yml` and `restore-drill.yml`) skips (b)/(c) with a loud warning; operator only. (a) is never skipped.
6. Runs `queued`/`pending` and created after the current run are waiting behind it in the group and do not count; `in_progress` and `waiting` do.
7. Fail closed: an API error or missing credential fails the job.
8. Race safety: the job runs inside the `drill` group the workflow already holds, so while (a)-(c) are evaluated no other group member can start, create or replace a VM. Only `rollback.yml` (own group, cannot create a VM) runs outside it and is covered by (a).

## Consequences

- A gate or restore drill dispatched while an explore drill is up fails fast at `drill-lock` instead of destroying it. Fix: wait for the TTL, or run `drill-destroy.yml`.
- A gate blocked by the lock posts `drill-gate` failure (apply skipped); re-dispatch after clearing the drill.
- Cancelled pending runs remain invisible; dispatch drills one at a time.
- The sweeper and destroy runs also fail when another drill run is active (a), even a short one; the next scheduled sweep retries.
- The lock job uses environment `drill-teardown` (ungated), so it never waits for approval. A missing `TS_CLEANUP_*` secret fails the lock (use `force` only as a knowing operator override).
