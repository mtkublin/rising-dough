# Restore Drill Log

Append one `## YYYY-MM-DD` entry per drill. Columns: operator, env, duration, result, notes.

Order: newest at top. Never edit a previous entry — if a drill log needs a correction, append a follow-up entry that references the dated entry it corrects.

Drill cadence is monthly per ADR-0034 §5.

**How entries get here (T-D41).** `main` is protected, so the workflow cannot commit. Every `restore-drill.yml` run that reached the restore job (pass or fail) writes its filled entry to the job summary and appends it as a comment on the single open issue titled `restore-log` (label `restore-log`; the workflow creates both when missing). Failed runs post `Result: fail`, and the `restore-drill-failure-YYYY-MM` issue is unchanged. The issue ([#28](https://github.com/mtkublin/rising-dough/issues/28)) is the log for automated runs, and future entries live there; this file keeps the manual entries (T-D40 and any ad-hoc drill), which the operator copies in by hand when a run should count for the T-D56 gate below.

`scripts/ci/litestream_cleanup.py` (T-D56 gate) reads only this file. It accepts an entry with a `## YYYY-MM-DD` heading, a `- **Result**: pass` line and a `- **integrity_check**: ok` line. To let an automated run satisfy the gate, copy its comment here.

The automated entry differs from the template in two fields: `Duration` runs from the workflow run start, and `Audit rows (prod)` is `n/a (prod not queried)` because CI has no read access to prod. The restored count, max id and max `changed_at` come from `audit_log` on the drill host (read-only).

## Template

```
## YYYY-MM-DD
- **Operator**: <handle or system-restore-drill>
- **Env**: drill-scratch-vm | prod-rebuild
- **Trigger**: scheduled-monthly | manual-ad-hoc | DR
- **Duration**: <m>m<ss>s (run start -> green /ready)
- **Source**: s3://<bucket>/db, generation <id>, snapshot index <n>, WAL index <a>..<b>, restored at <utc>
- **Audit rows (prod)**: <count>, max_id=<n>, max_changed_at=<utc> | n/a (prod not queried)
- **Audit rows (restored)**: <count>, max_id=<n>, max_changed_at=<utc>
- **integrity_check**: ok | failed-<detail>
- **Recovery point**: latest | 2026-11-15T08:00:00Z
- **Result**: pass | fail
- **Notes**: free text — any deviations, timing surprises, workflow run url.
```

<!-- Entries below this line. -->

## 2026-11-18
- **Operator**: system-restore-drill
- **Env**: drill-scratch-vm
- **Trigger**: manual-ad-hoc (dispatched from `main`, T-D41 proof; automated post on issue #28)
- **Duration**: 5m26s (run start -> green /ready)
- **Source**: s3://budget-planner-prod-pl-waw/db, generation 2901fbd3873a6696, snapshot index 0, WAL index 0..10, restored at 2026-11-18T20:09:55Z
- **Audit rows (prod)**: n/a (prod not queried)
- **Audit rows (restored)**: 293, max_id=293, max_changed_at=2026-11-18T11:58:26.101Z
- **integrity_check**: ok
- **Recovery point**: latest
- **Result**: pass
- **Notes**: workflow run https://github.com/mtkublin/rising-dough/actions/runs/44387134093, dispatched from `main` at b018739. All jobs green; "Open issue on failure" skipped. Entry also posted as a comment on the `restore-log` issue ([#28](https://github.com/mtkublin/rising-dough/issues/28)). App image ghcr.io/mtkublin/budget-planner:v3.0.3@sha256:bef6512523df4c67727a5d443b01baf3384ad1d1793bad81e5ca5a9e563f4864, /ready ready-ok. T-D57: no extra DB copies. The same run is the T-D138 positive leg (drill lock passed after the explore drill was destroyed).

## 2026-11-18
- **Operator**: system-restore-drill, dispatched by the orchestrator with operator approval
- **Env**: drill-scratch-vm
- **Trigger**: manual-ad-hoc (first drill, T-D40)
- **Duration**: about 6 min (drill VM apply to green /ready; job start 16:46Z, /ready 16:52Z)
- **Source**: s3://budget-planner-prod-pl-waw/db, encrypted generation 2901fbd3873a6696, snapshot index 0, WAL index 0..3, restored at 2026-11-18T16:51:52Z (the restore took 19s). App image v3.0.2.
- **Audit rows (prod)**: n/a (prod not queried)
- **Audit rows (restored)**: not collected (the workflow had no count step; added by T-D41 for later runs)
- **integrity_check**: ok
- **Recovery point**: latest (newest WAL segment in the replica at restore time)
- **Result**: pass
- **Notes**: workflow run https://github.com/mtkublin/rising-dough/actions/runs/44351020259, dispatched from `docs/v3-remaining` at 9257b5b. /ready: status=ready db=ok. T-D57: no extra DB copies. Three earlier attempts failed on drill-script bugs, not on backup data: 44330551119 (ready check URL/status), 44340976282 (RETURN trap), 44346338885 (tmp-wal/shm leftovers); all fixed in T-D40-FIX/FIX2/FIX3. The app image does not serve `/health/replication` yet (v3.0.2).
