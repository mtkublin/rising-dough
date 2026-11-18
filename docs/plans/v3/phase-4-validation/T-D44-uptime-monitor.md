# T-D44: Uptime monitoring

Status: ✅ (2026-11-18). Task entry: [`../tasks.md`](../tasks.md) T-D44.

## Decision history

- 2026-11-16 (user): a scheduled GitHub Actions workflow, `uptime.yml`, checks `/health` and the host agent status every 5 min.
- 2026-11-18: `gh run list` shows about 3 scheduled runs in roughly 28 h, not about 330. GitHub throttles `*/5` schedules, so the workflow cannot give timely detection on its own. Recommended option: an external monitor (task entry, option 1).
- 2026-11-18 (operator): an external UptimeRobot monitor for https://budget.rising-dough.eu is set up. It is the primary alarm.
- 2026-11-18 (user): `.github/workflows/uptime.yml` is dropped. UptimeRobot is the only uptime alarm. Accepted trade-off: no alert when host-agent convergence fails while `/health` is still ok. Release and rollback runs show that state instead.
- 2026-11-18 (user): host-down detection is covered by the external `/health` check, which fails when the host is down. Option 4 (host-side dead-man's switch) is not needed.

## Done

- External UptimeRobot monitor on https://budget.rising-dough.eu, 5 min interval, checking `/health`. Operator received a test alert e-mail (2026-11-18). Monitor identifier and contact details are not recorded here.
- `.github/workflows/uptime.yml` removed (2026-11-18). Its test `tests/unit/deploy/test_uptime_workflow.py` removed with it.
- Host-down detection: covered by the external check. Option 4 not needed.

## Done-definition (met)

Interval, monitored path, alert delivery and the `uptime.yml` decision are recorded above. Host-down detection is covered by the external check.

## Runbook

[`../runbooks/disaster-recovery.md`](../runbooks/disaster-recovery.md) (section on the uptime monitor).
