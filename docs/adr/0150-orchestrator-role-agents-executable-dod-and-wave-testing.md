# ADR-0150: Orchestrator v2: Role Agents, an Executable Definition of Done and One Test Run per Wave

- **Status**: Accepted
- **Date**: 2026-11-24
- **Amends**: [ADR-0066](0066-orchestrator-mode-skill.md) (orchestrator scope, model choice, briefs, merge review); [ADR-0120](0120-pre-commit-is-the-local-gate.md) §1 and amendment 2026-11-22 (the test gate for orchestrated item agents only)
- **Related**: [ADR-0097](0097-per-batch-ci-policy-and-fast-precommit-pytest.md), [ADR-0099](0099-release-and-environment-policy.md), [ADR-0108](0108-faster-ci-parallel-tests-and-change-based-inner-loop.md), [ADR-0130](0130-prevention-regime-and-full-architectural-compliance.md) §7
- **Tasks**: T-Q324 to T-Q329 (`docs/plans/quality-audit/tasks.md`)

## Context

The orchestrator-mode skill (ADR-0066) has grown to about 300 lines of prose, plus a shared brief. Runs since 2026-11-19 keep showing the same failures, even though each one is already written down as a rule:

- **CPU.** Each item agent runs the pytest hook on every commit. A docs commit runs the full suite (the `_unseen-paths` fallback). With N agents that is N parallel suites. Load reached 50 to 110 on 8 cores more than once. One cause was an agent using `-n auto` although the brief said not to, so a prose rule did not prevent it.
- **Orchestrator context.** The orchestrator reads diffs, `rg` output and long reports to check each item (duplication, scope, audit record, allowlists). That fills its context and is mostly mechanical.
- **Model mix.** Almost every agent runs on Sonnet. Haiku is allowed for "mechanical" items, but briefs are long and the items mix code with doc bookkeeping, so few items qualify.
- **Hotspots.** Under the docs-first rule nearly every item edits `tasks.md`, `CHANGELOG.md` and the ADR index. These are the usual merge conflicts, and each of these edits triggers a full-suite hook run.
- **No measurements.** There is no record of wall time, retries or model per item, so changes to the model mix or to item sizing cannot be judged.

The operator proposed (2026-11-24): an orchestrator that only plans, dispatches and checks; atomic work; more Haiku; hard contracts (DoR, DoD, acceptance criteria) between the orchestrator, the agents and the human; testing moved out of the implementers into a dedicated tester per wave; and specialized agent types. The review accepted these with changes (below). The operator accepted the review as written.

## Decision

### 1. The orchestrator plans, dispatches, merges and reads verdicts

The orchestrator writes no repo files (unchanged). It also stops reviewing diffs itself. Per item it reads two things: the output of `scripts/ci/check_item.py` (§4) and the `reviewer` agent's verdict. Merging stays with the orchestrator, because `just merge-item` is a deterministic script (T-Q304). Trivial conflict hunks stay with it as well (ADR-0066). A semantic conflict goes to an `implementer`.

### 2. Role agents in `.claude/agents/`, split by role, not by tech layer

Each role is a subagent definition. Its frontmatter pins the model and restricts the tools, and the role's standing rules live in its system prompt. This replaces most of `brief-common.md`:

| Agent | Model | Tools | Job |
|---|---|---|---|
| `explorer` | haiku | read-only | Research for planning. Returns `file:line` facts, no fixes. |
| `implementer` | sonnet | full | Code, tests and ADR or requirement text for one item, in its own worktree, within the files it owns. Also takes over a stuck worktree or resolves a semantic conflict. |
| `scribe` | haiku | full, docs only by rule | Wave bookkeeping: `tasks.md` ✅ marks, `CHANGELOG.md` lines, ADR index rows, and the run log (§7). |
| `reviewer` | sonnet | read-only plus Bash | Runs `check_item.py` and checks what the script cannot: reuse of canonical modules, guard-gaming, test values, brief compliance. Returns `MERGE` or `RETURN` with evidence. |
| `tester` | haiku | Bash, no edits | The wave test run (§5). Reports failing node ids and the merge commit each one is blamed on. |
| `visual-auditor` | sonnet | full | Runs the `frontend-visual-audit` skill on an item's worktree and commits `docs/audits/<date>-<id>.md`. Does not fix templates. |

- **Not split by layer.** Slices in this repo are vertical (router, service, template, test), so `ui-dev` and `backend-dev` agents would create handoffs inside one feature. A template item is an `implementer` item followed by a `visual-auditor` run in the same worktree, so the implementer does not carry the audit skill.
- **No devops agent.** Prod, GitHub settings and drills are gated on the operator (ADR-0099). Ops items are `implementer` items, and every operator step goes into the human contract (§4).
- **Model override.** The `model` given on the Agent call overrides the frontmatter. The orchestrator passes `model: "haiku"` to an `implementer` for items that pass the Haiku test (§3).

### 3. Atomic steps inside an item; items have a size floor; the Haiku test

- **Not more agents.** Each agent has a fixed overhead (worktree, `just worktree-init`, reading the brief, a merge). A finer split also multiplies hotspot conflicts. An item stays one coherent change, under about 1 h (ADR-0066 amendment 2026-11-22), and at least one commit of real code or doc content. Bookkeeping is not an item: the scribe does it.
- **Atomic steps.** The brief's body is a numbered step list. Each step names its file and function and a check (a command with its expected result). The agent works through the list in order and reports each step.
- **Haiku test.** An `implementer` item goes to Haiku when all of the following hold:
  - it touches at most 2 files of source plus their tests;
  - it adds no new public function and no schema, SQL or migration change;
  - each step copies an existing pattern the brief names by `file:line`;
  - its acceptance criteria are commands.

  Every `explorer`, `scribe` and `tester` run is Haiku by definition.
- **Escalation ladder.** If Haiku fails an item once, the retry runs on Sonnet. If Sonnet fails the same item twice, the next try runs on Opus. Each escalation goes in the run log.

### 4. Contracts: Definition of Ready, an executable Definition of Done, a report schema, a human contract

- **Definition of Ready.** The orchestrator dispatches an item only if its brief has:
  - the goal and the task id;
  - the files it owns and the files it must not touch;
  - pre-assigned ADR and migration numbers;
  - the numbered steps (§3);
  - acceptance criteria written as commands (pytest node ids, `rg` expectations, `just` recipes);
  - the base sha, the heavy-lock name and the model.

  An item that fails this goes back to planning or to an `explorer` first.
- **Definition of Done = `scripts/ci/check_item.py <ID>`.** The script checks mechanically:
  - the item branch exists and is ahead of the work branch;
  - every changed file is in the owned list;
  - scribe hotspots are untouched unless the item is the scribe's;
  - commit subjects follow `type(<ID>...):`;
  - allowlist totals did not rise;
  - added suppressions are listed;
  - a template or CSS change adds a `docs/audits/*.md` record;
  - new top-level definitions are listed, flagged when the name looks like a Canonical modules concept.

  Its exit code decides. The handoff checklist in CLAUDE.md stays the human-readable DoD. The script automates the parts of it that can be checked without judgment.
- **Report schema.** Every role ends with the same block: `STATUS` (`DONE` / `PARTIAL` / `BLOCKED`), `BRANCH`, `SHA`, `STEPS` (one line per step with its check result), `CHECKS` (command and exit code), `SEARCHED/REUSED/NEW_HELPER`, `ALLOWLISTS`, `LEFT`, `QUESTIONS`. Prose goes after the block. The orchestrator acts on the block alone.
- **Human contract.** The orchestrator stops and asks the operator only for:
  - anything that touches prod or `data/budget.sqlite`;
  - pushing to `main`, opening a PR, or marking one ready;
  - GitHub settings, rulesets, secrets, or drill dispatch outside the gate;
  - scope creep into v2 or out-of-scope items (requirements §3.8);
  - an item that failed on Opus (§3);
  - a decision the requirements and ADRs do not settle.

  Every other question goes into the run's deferred-questions list and is asked at the end. Before any count is reported to the operator, it is derived from a command.

### 5. One test run per wave; implementers commit without the pytest hook

Applies to item agents in an orchestrated run only. Single-agent work keeps ADR-0120 unchanged.

- **Item agents commit with `SKIP=pytest-fast`.** All other hooks still run: ruff, ruff-format, mypy, import-linter, sqlfluff, djlint, stylelint, bandit, detect-secrets. While developing, an agent runs only the test files it writes or names in its steps, serially (`-p no:xdist`). `--no-verify` stays banned.
- **The wave tester.** When every item of a wave is merged, and no merge or agent is in flight, the orchestrator dispatches one `tester`. The tester takes the heavy lock and runs `just test-changed <wave-base-sha>` in the main checkout. That command uses testmon selection, or the full suite when the wave changed a path testmon cannot see. The tester then runs the wave e2e (`just test-e2e`, ADR-0120 amendment 2026-11-22) and reports. Result: one suite run per wave instead of one per commit.
- **Failures.** The tester blames each failing test on the `merge(<ID>)` commit that introduced it (by the files the test covers, or by reverting merges in a scratch worktree when that is unclear). The orchestrator dispatches an `implementer` with the failing node ids. The fix is merged, and the tester runs again. The next wave does not start on a red work branch.
- **Trade-off accepted.** A failure surfaces after the implementer has exited, so the fix costs a fresh agent. In return the per-commit suite runs go away, which were the main CPU cost. The gap ADR-0120 already noted (a clean merge runs no hooks) is closed: merged combinations are now tested per wave. PR CI stays the full gate.

### 6. The worker cap is enforced in code

A `pytest_xdist_auto_num_workers` hook in `tests/conftest.py` makes `-n auto` resolve to 2 workers when pytest runs inside a linked git worktree (`.git` is a file, not a directory). It covers `just` recipes and direct `pytest -n auto` calls alike. The main checkout and CI keep `auto`. An explicit `-n <n>` or `PYTEST_WORKERS` still wins. Briefs keep `PYTEST_WORKERS=2` as a second layer.

### 7. Run log

At the end of each run the scribe commits `docs/runs/<date>-<slug>.md`. It has one row per agent run (item, role, model, wall time from the completion notification, attempts, verdict, escalations), plus the wave test results and the peak load the orchestrator recorded. Changes to the model mix (§3) are judged against these logs.

### 8. The skill becomes a flow

`.claude/skills/orchestrator-mode/SKILL.md` keeps only the flow: Step 0 branch, plan and DoR, dispatch, review, merge, wave test, scribe, finish. It also keeps the machine-load and supervision rules that only the orchestrator applies. Role rules live in the agent definitions. `brief-common.md` shrinks to the item-brief template.

## Consequences

- The orchestrator's per-item context is one script output and one verdict instead of diffs.
- CPU use per wave drops from N hook suites to one tester run. A docs commit no longer runs the full suite in an orchestrated run.
- Bookkeeping hotspots get a single writer per wave, so most append-only conflicts disappear.
- More runs go to Haiku: every explorer, scribe and tester run, plus implementer items that pass the Haiku test. Whether Haiku implementer items pay off is measured in the run logs, not assumed.
- Implementers lose the per-commit test feedback. Mitigation: running their own test files, and the tester's blame step.
- Agent definitions are prompts. They drift if the repo rules change. CLAUDE.md stays the source of the rules, and the agent files link to it.

## Alternatives considered

- **Split work into many atomic agents.** Rejected: per-agent overhead, more hotspot conflicts and more merges for the same change. Atomic steps inside a brief give a small model the same simplicity.
- **Layer agents (`ui-dev`, `backend-dev`, `fullstack-dev`).** Rejected: vertical slices would need handoffs inside one feature.
- **A `devops` agent.** Rejected: ops work is gated on the operator (ADR-0099), so the agent would mostly be blocked.
- **Keep the pytest hook in item agents and add the wave tester on top.** Rejected: it keeps the N-suites CPU cost the change exists to remove.
- **Encode the wave loop as a `Workflow` script.** Deferred: it needs explicit opt-in per run, and worktree isolation for workflow agents has not been confirmed. Revisit once the run logs show the flow is stable.
- **More prose rules in the skill.** Rejected: the incidents happened with the rule already written down. Enforcement moves to scripts, frontmatter and the conftest hook.

## Amendment 2026-11-25: no idle turns

Incident (`ui/sourdough` run): the orchestrator ended its turn with one agent in flight. The agent finished about 07:46, but the orchestrator resumed only at 09:17, when the operator wrote ("why did you stop in the meantime? you were supposed to keep running until PR ready").

Rule, in the `orchestrator-mode` skill §5 and §6: in a run told to keep going, before ending any turn the orchestrator has (a) at least 2 agents in flight when load allows and unblocked work exists, and (b) a background heartbeat timer running (`sleep 1200; echo heartbeat`, Bash `run_in_background`, restarted on every heartbeat). A completion notification can fail to arrive; the heartbeat re-invokes the orchestrator to check worktrees, merge and dispatch. A turn whose only in-flight work is one agent waiting on its own background job is never ended. An operator question mid-run is answered and the run continues in the same turn. The single heartbeat is not a polling loop; "no polling" stays.
