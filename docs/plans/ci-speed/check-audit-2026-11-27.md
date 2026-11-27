# CI Check Audit (2026-11-27)

> Plan: [README.md](README.md). Tasks: [tasks.md](tasks.md) (T-CS10…T-CS17, proposed). Policies: [ADR-0099](../../adr/0099-release-and-environment-policy.md) (release, drill gate), [ADR-0108](../../adr/0108-faster-ci-parallel-tests-and-change-based-inner-loop.md), [ADR-0120](../../adr/0120-pre-commit-is-the-local-gate.md), [ADR-0121](../../adr/0121-path-filtered-workflows-are-not-required-checks.md), [ADR-0130](../../adr/0130-prevention-regime-and-full-architectural-compliance.md) §8, [ADR-0154](../../adr/0154-accepted-ui-screenshots-replace-the-handoff-references.md).

## Problem

PR #54 (`ui/sourdough`) shows **29 checks** per push. Seven are required. Several jobs repeat work that another job on the same SHA already did, and the drill gate repeats the PR's whole `ci` workflow before it builds. Status is documented here; nothing is changed yet. Each fix is a proposed task below, and the ones that change the job layout or the required checks need an ADR first.

## Method

- Check list and durations: `gh pr checks 54` and `gh pr checks 62` (2026-11-27).
- Workflow structure: every file in `.github/workflows/` on `ui/sourdough` at `bcf445c2` (triggers, jobs, `needs`, matrices, run steps).
- Required checks: `protect-main` ruleset (`gh api repos/<owner>/<repo>/rulesets/<id>`).
- Drill: jobs of run `45987714192` (`drill.yml`, explore, `wi/ui/sourdough/YEARUX`, 2026-11-27).
- Test durations: local `pytest tests/visual tests/ui_map tests/unit/deploy -n 4 --no-cov --durations=0` (2,042 tests). Local times rank tests only; GitHub is the absolute reference (`baseline.md` "Method").

## The 29 checks on PR #54

Wall times are from the latest push. "Req" = in the `protect-main` ruleset.

| # | Check | Workflow | Req | Time | Notes |
|---|---|---|---|---|---|
| 1 | `just ci (Python 3.12, ubuntu-latest)` | ci.yml | yes | 10m24s | pre-commit `--all-files` then `just ci` (D1) |
| 2–5 | `pytest (shifted clock)` × 4 | ci.yml | no | 3m10s–4m12s | full non-e2e suite each (D2) |
| 6 | `tests/e2e (Chromium, Playwright container)` | e2e.yml | yes | 5m35s | |
| 7–8 | `tests/e2e (firefox / webkit, advisory)` | e2e.yml | no | 43s / 7m56s | full e2e again per engine (D6) |
| 9 | `a11y (axe-core, advisory)` | a11y-perf.yml | no | 49s | one e2e file, own server boot (D6) |
| 10 | `perf (Lighthouse budgets, advisory)` | a11y-perf.yml | no | 6m16s | one e2e file plus Caddy (D6) |
| 11 | `classify changed files` | visual.yml | no | 6s | |
| 12 | `visual suite (pinned Playwright container)` | visual.yml | no | 49s | |
| 13–18 | `handoff reference comparison <shard> (advisory)` × 6 | visual.yml | no | 6m57s–8m3s | **all six failing**, scheduled for removal (D5) |
| 19 | `visual-gate` | visual.yml | no | 3s | |
| 20 | `pip-audit (uv.lock)` | security.yml | yes | 14s | |
| 21 | `trivy fs (repo)` | security.yml | yes | 35s | scans twice (D4) |
| 22 | `trivy image (rising-dough:scan)` | security.yml | yes | 1m54s | builds the image, scans twice (D4) |
| 23 | `Trivy` | code scanning | no | 3s | SARIF result of 21/22 |
| 24 | `uv lock --check` | lock-check.yml | yes | 7s | own runner for a 1 s command (D7) |
| 25 | `fmt + validate + lint` | terraform.yml | no | 38s | path-filtered (`terraform/**`) |
| 26–27 | `plan (drill)`, `plan (prod)` | terraform.yml | no | 20s, 22s | path-filtered |
| 28 | `apply (${{ inputs.env }})` | terraform.yml | no | skipped | a `workflow_call`-only job that still shows on the PR (D9) |
| 29 | `drill-gate skip check` | drill-gate-skip.yml | no | 11s | posts `drill-gate` for non-deploy PRs |

Required (7): `drill-gate`, `just ci`, `uv lock --check`, `pip-audit`, `trivy fs`, `trivy image`, `tests/e2e (Chromium)`. **22 of the 29 checks are not required.**

### Runner minutes per push (PR #54, approximate, from the table)

| Group | Runner min | Required? |
|---|---|---|
| Handoff reference × 6 | ~45 | no, failing |
| Shifted clock × 4 | ~15 | no |
| e2e Firefox + WebKit | ~9 | no |
| a11y + perf | ~7 | no |
| `just ci` | ~10 | yes |
| e2e Chromium | ~6 | yes |
| Security (pip-audit, trivy × 2) | ~3 | yes |
| Terraform, visual, classify, skip, lock | ~3 | mixed |
| **Total** | **~98** | required ≈ 19 (about 20%) |

A docs-only PR (#62, on `main`) still runs 20 checks: `just ci` (4m04s), four shifted-clock runs, three e2e engines, a11y, perf and the image build, which together is about 40 runner-minutes for a Markdown change.

## Duplications and waste

### D1. Lint and mypy run twice in the `just ci` job

`ci.yml` runs `pre-commit run --all-files` (ADR-0130 §8: ruff, ruff-format, mypy, sqlfluff, djlint, bandit, xenon, detect-secrets, lint-imports, stylelint, css-bundle-check) and then `just ci`, which is `lint typecheck test`. `just lint` reruns ruff, lint-imports, xenon, sqlfluff, djlint and stylelint, and `just typecheck` reruns `mypy src tests`. **Seven tools run twice** on the same tree, in series, in the required job.
**Fix**: CI runs the hooks and then only `just test`. `just ci` stays the full local recipe. The only change is to `ci.yml`.

### D2. The shifted-clock matrix reruns the whole suite four times

T-Q311 (ADR-0140 amendment 2026-11-23) runs the suite at four dangerous instants to catch date-dependent tests. Each run takes every non-e2e test (about 6,300): architecture guards, deploy-script tests, ui_map, the handoff overlay and so on, none of which read the clock. That is about 15 runner-minutes per push, and the 100 s overlay test (D10) sets the floor of each run.
**Fix options** (pick one, ADR-0140 amendment): (a) select only the tests that depend on the clock (domain, services, web integration and contract; exclude `tests/architecture`, `tests/unit/deploy`, `tests/visual`, `tests/ui_map`); (b) run the matrix on `push` to `main` plus a daily schedule instead of every PR push; (c) both.

### D3. The drill gate reruns the PR's whole CI

`drill.yml` (gate and explore) calls `ci.yml` through `workflow_call` before `build`. On the same SHA the PR already ran `just ci` and the four shifted-clock jobs. In run `45987714192`, that call took **9m19s** (11:06:51 → 11:16:10) before the image build started, out of about 17 minutes in all. All that time the run holds the shared `drill` lock and concurrency group, so other drills wait behind tests that have already passed. `release.yml` calls `ci.yml` too (tag → ci → build → apply prod). That call is defensible: a tag sits on a merge commit that no PR run tested.
**Fix**: before `build`, the drill gate checks that the required checks (`just ci`, `tests/e2e (Chromium)`) succeeded on the head SHA (`gh api .../commits/<sha>/check-runs`) and fails if they did not. That takes seconds instead of 9 minutes. Explore mode can skip the check entirely. Needs an ADR-0099 amendment, because the gate currently proves CI itself.

### D4. Docker image and Trivy scans are repeated

- `trivy fs` runs `trivy-action` twice on the same tree, once as a table and once as SARIF (`security.yml` lines 147 and 164). `trivy image` does the same (lines 242 and 259).
- `trivy image` builds the Dockerfile on every PR, even docs-only. `build.yml` in the drill builds the same SHA again to push it.
- `terraform.yml` `fmt-validate` runs a third Trivy pass (`scan-type: config`, `terraform/`). That one does not overlap: it covers IaC config only.

**Fix**: one scan per target. Write the SARIF once and fail with `--exit-code 1` on the same run, or run `trivy convert` on its JSON. Skip the image build and scan when the Dockerfile, `uv.lock`, `src/` and `migrations/` are unchanged; under ADR-0121, a check that is path-filtered or skipped must still report a result. A `changes` job plus a gate job does that, like `visual-gate`.

### D5. The handoff reference comparison is the biggest single cost, and it is advisory and failing

Six shards take 7–8 minutes each, about 45 runner-minutes per push, and all six fail on PR #54. ADR-0154 §5 and T-UR66 already decided to move the `reference` job off the per-PR path (`schedule` and `workflow_dispatch` only). That change is blocked only because agents lack the workflow scope; the operator patch is in `docs/plans/ui-redesign/q-visual-reference-trigger.md`.
**Fix**: apply T-UR66. Nothing new to decide.

### D6. Advisory browser jobs run on every PR push

- `e2e-browsers` (Firefox, WebKit) runs the whole e2e suite again per engine on every push, including docs-only PRs.
- `a11y` and `perf` each boot their own server for one file in `tests/e2e/`. The required e2e job collects the same files and skips them by environment variable (`A11Y_SWEEP`, `PERF_LHCI`).
- `e2e.yml` and `a11y-perf.yml` also run on `push` to `wi/**`, so an orchestrated item runs them once on its branch and again on the PR.

**Fix**: run the advisory engines, a11y and perf only when frontend paths change (same classifier as `visual.yml`), plus a weekly schedule. Fold a11y into the Chromium e2e job (`A11Y_SWEEP=1` in that job) to save a server boot and a runner.

### D7. Lock check runs on its own runner

`lock-check.yml` spends about 7 s of runner time (checkout plus uv) on `uv lock --check`. Every other job runs `uv sync --frozen`, which does not check the lock. If `ci.yml` ran `uv sync --locked`, `just ci` would fail on a stale lock and the separate job could go. It is a required check, so removing it is a ruleset change (operator, ADR-0121 note). This is minor; list it only if the ruleset is touched for other reasons.

### D8. Every reusable Terraform call repeats `fmt-validate`

`terraform.yml` `apply` `needs: fmt-validate`, so every `workflow_call` reruns `fmt`, `validate`, `terraform test`, the cloud-init render check, tflint and Trivy config (about 33 s each). A gate drill calls `terraform.yml` four times: baseline, upgrade, rollback and teardown. An explore drill calls it once for apply and once for teardown. The terraform tree is identical across those calls, except for the baseline call, which uses `terraform_ref`.
**Fix**: run `fmt-validate` only on `pull_request`, plus once per drill run for the PR tree.

### D9. The `apply` job shows on PRs as skipped

`terraform.yml` runs on `pull_request` (terraform paths) as well as `workflow_call`. Its `apply` job is call-only but still appears as `apply (${{ inputs.env }}) — skipping` with an unrendered name. This is noise only.
**Fix**: give the job a static name, or split the PR checks from the reusable workflow.

### D10. One 100-second serial test sets the floor of every pytest job

`tests/visual/test_handoff_overlay.py::test_overlay_changes_only_text_and_allowed_attributes` takes **99.9 s** on its own, and `test_no_stale_today_key_after_overlay` takes **15.3 s**. Together they are 85% of the 138 s CPU time of `tests/visual`. xdist cannot split a single test, so this one sets the minimum length of `just ci` and of each of the four shifted-clock runs. The loop parses the pristine page with BeautifulSoup once per row inside its page loop, at about lines 166–168: (pages × rows) parses where one per page would do. This likely explains part of the jump from `just ci` at about 2 minutes (T-CS08) to 10m24s on `ui/sourdough`, against 4m04s on `main`, which lacks these tests. Not yet measured on GitHub.
**Fix**: parse once per page. If ADR-0154 is accepted, the overlay tests leave the suite with the handoff comparison anyway.

## Questions from the same session

- **Would subtests cut the count cheaply?** Yes, they cut the count, but not the time. pytest 9.1 has `subtests` built in. The 409 cases of `test_row_follows_the_rules` sum to 0.00 s of call time, so merging them saves only per-item overhead and costs the xdist spread and per-row testmon selection. It fits pure data-row tests (`test_handoff_overlay`, `test_overlay_values`, ui_map `test_name_resolves_in_handoff`, `test_workflow_script_paths`) as a cleanup for the count. It does not fit DB- or HTTP-backed cases (`test_user_isolation`, `test_ledger_access`), which keep the xdist spread. It is not a speed fix: D10 is.
- **Do the deploy tests belong in the main suite?** Yes. All 59 files of `tests/unit/deploy` together take 31.5 s CPU locally; the slowest are `test_drill_gate_upgrade.py` at 8.5 s and `test_replace_rehearsal.py` at 7.1 s. Under xdist that is a few seconds of wall time, and they guard workflows and scripts that run on every PR. The only overlap is D2: they need not run in the shifted-clock matrix.

## Proposed order

By runner minutes saved per push, lowest risk first:

1. **D5** (T-UR66, decided): about 45 min per push. Operator applies the workflow patch.
2. **D2**: about 10–15 min per push, plus shorter wall time per run.
3. **D6**: about 16 min on non-frontend pushes.
4. **D3**: about 9 min of drill wall time and drill-lock hold per drill.
5. **D10**: about 100 s off the critical path of `just ci` and each shifted-clock job.
6. **D1**: tens of seconds of required-job wall time.
7. **D4, D8, D9, D7**: small savings, mostly fewer checks shown.

Combined, D5 + D2 + D6 take a docs-only or backend PR from 20–29 checks and about 98 runner-minutes down to roughly 10 checks and under 25 minutes, with the required set unchanged.
