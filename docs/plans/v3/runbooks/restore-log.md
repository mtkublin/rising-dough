# Restore Drill Log

Append one `## YYYY-MM-DD` entry per drill. Columns: operator, env, duration, result, notes.

Order: newest at top. Never edit a previous entry — if a drill log needs a correction, append a follow-up entry that references the dated entry it corrects.

Drill cadence is monthly per ADR-0034 §5. The automated workflow (`.github/workflows/restore-drill.yml`, T-D41) appends an entry on success; manual drills (T-D40 and any ad-hoc) are entered by the operator.

## Template

```
## YYYY-MM-DD
- **Operator**: <handle or system-restore-drill>
- **Env**: drill-scratch-vm | prod-rebuild
- **Trigger**: scheduled-monthly | manual-ad-hoc | DR
- **Duration**: <mm'ss"> (terraform apply → green /ready)
- **Audit rows (prod)**: <count>, max_id=<n>, max_created_at=<utc>
- **Audit rows (restored)**: <count>, max_id=<n>
- **integrity_check**: ok | failed-<detail>
- **Recovery point**: latest | 2026-11-15T08:00:00Z
- **Result**: pass | fail
- **Notes**: free text — any deviations, timing surprises, workflow run url.
```

<!-- Entries below this line. -->
