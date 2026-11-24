# Orchestrator run logs

One file per orchestrated run, `docs/runs/<YYYY-MM-DD>-<slug>.md`, written by the `scribe` at the end of the run from values the orchestrator hands it ([ADR-0150](../adr/0150-orchestrator-role-agents-executable-dod-and-wave-testing.md) §7). The logs are the evidence for changing the model mix or item sizing: compare first-pass rates and wall times per role and model across runs, never quote them from memory.

Rules:

- Every value comes from a command or a completion notification (wall time = the notification's `duration_ms`). An unknown value is `?`, never an estimate.
- One row per agent run, including retries and escalations (a retried item has several rows).
- `verdict` is the role's report status (`DONE`, `PARTIAL`, `BLOCKED`, `MERGE`, `RETURN`, `GREEN`, `RED`, `CLEAN`, `FINDINGS`).

## Template

```markdown
# Run <YYYY-MM-DD> <slug>

- Work branch: `<MAIN>`; base `<sha>`; PR: #<n> | none
- Request: <one line>
- Waves: <n>; items: <n>; agent runs: <n>

## Agent runs

| wave | item | role | model | attempt | wall time | verdict | note |
|---|---|---|---|---|---|---|---|
| 1 | T-X1 | implementer | haiku | 1 | 12 min | DONE | |
| 1 | T-X1 | reviewer | sonnet | 1 | 4 min | RETURN | reuse: month window |
| 1 | T-X1 | implementer | sonnet | 2 | 9 min | DONE | escalated haiku -> sonnet |

## Wave tests

| wave | base..head | test-changed | test-e2e | failures (blamed item) |
|---|---|---|---|---|
| 1 | `abc1234..def5678` | rc=0 (812 passed) | rc=0 | none |

## Load and incidents

- Peak 5-min load: <n> on <cores> cores (`uptime` at <time>).
- Stuck or stopped agents, overruns past 1 h, lock waits: <list | none>.

## Escalations and deferred questions

- <item>: <from model> -> <to model>, <reason>
- Deferred questions asked at the end: <n> (<link or list>)
```
