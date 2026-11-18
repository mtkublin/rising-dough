# T-D44: Uptime monitoring

Status: ◐ partial (2026-11-18). Task entry: [`../tasks.md`](../tasks.md) T-D44.

## Decision history

- 2026-11-16 (user): a scheduled GitHub Actions workflow, `uptime.yml`, checks `/health` and the host agent status every 5 min.
- 2026-11-18: `gh run list` shows about 3 scheduled runs in roughly 28 h, not about 330. GitHub throttles `*/5` schedules, so the workflow cannot give timely detection on its own. Recommended option: an external monitor (task entry, option 1).
- 2026-11-18 (operator): an external UptimeRobot monitor for https://budget.rising-dough.eu is set up. It is the primary alarm. `uptime.yml` stays as a backup until the user decides otherwise.

## Done

- External monitor exists (operator, 2026-11-18). Its identifier and contact details are not recorded here.
- `.github/workflows/uptime.yml` exists on `main` (backup role).

## Not yet recorded (needed before ✅)

- Check interval. The decision requires 1 to 5 min.
- Monitored path and the condition that counts as down (HTTP status, or the host agent status file as in `uptime.yml`).
- Alert delivery: one test down/up with the alert e-mail received.
- Decision on `uptime.yml`: keep as backup, or drop.
- Host-down detection, if wanted: option 4 in the task entry (host-side dead-man's switch). Not decided.

## Done-definition

Status moves to ✅ when the external monitor's interval, path and alert delivery are recorded here and the `uptime.yml` decision is made. Host-down detection is optional and is decided separately.

## Runbook

[`../runbooks/disaster-recovery.md`](../runbooks/disaster-recovery.md) (section on the uptime monitor).
