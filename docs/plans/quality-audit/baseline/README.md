# Phase 1 baseline: static tool run (T-Q02)

Pinned commit `AUDIT_SHA = 9fb18cbca26ef305855efc8fc106d896edc82631`. All tools ran in report-only mode in the audit worktree. No dependency, lockfile or config change was committed (extra tools came from `uv run --with` / `uvx` / `npx`; tflint was a one-off release binary kept outside the repo). No tool opened `data/budget.sqlite`: scans were source-tree only and secret scans excluded `data/*.sqlite`. Raw output sits next to this file. The pass raised no Critical suspicion: the secret scan hits are all false positives (see detect-secrets).

Not in this file set, written by other tasks:
- `ci.txt`, `coverage.txt`: T-Q01 (coverage by module, CI timings).
- `mutmut-spike.md` (and later `mutmut.txt`): T-Q03a / T-Q03b.

## Tools

**Suppressions** (`suppressions.txt`; plain grep; feeds B, C). `src` carries 126 `noqa` comments by code: PLC0415 37, PLR0917 32, DTZ011 18, PLR2004 6, PLR0911 6, S105 5, PLR0915 4, N818 4, PLR0912 3, E402 3, S704 2, PLW0603 2, B008 2, S104 1, ARG001 1. No bare `noqa`. Also 5 `type: ignore`, 27 `pragma: no cover`, 1 `nosec`. Densest files: `web/routers/recurring.py` (17), `services/recurring.py` (16), `services/recurring_formula.py` (12), `web/routers/planned.py` (9), `web/routers/auth.py` (8). The recurring cluster stands out.

**Extended ruff** (`ruff-all.txt`; `ruff 0.17.2`, `check --select ALL --statistics --no-cache`, run separately on `src` and `tests`; feeds B, C). Project `ignore` entries still apply, and `noqa`-suppressed hits are not counted. `src`: 1395 findings. The leading rules are mostly style: FAST002 321 (non-annotated FastAPI dependency), COM812 190, D103 122, CPY001 120, TC003 103, TRY003 90. Structural ones: PLR0913 too-many-arguments 66, ANN401 `Any` 32, C901 10, BLE001 blind-except 3, S101 assert 32. `tests`: 3949 findings, mostly D103 (2018), COM812, CPY001, PT018/PT019; BLE001 6.

**Complexity and maintainability** (`radon-cc.txt`, `radon-mi.txt`, `xenon.txt`; `radon 6.0.1`, xenon with `--max-absolute B --max-modules B --max-average A`; feeds B). 927 blocks, average complexity A (3.06). 33 blocks rank C or worse, of which 2 are above C: `web/routers/plan.py:68 plan` is E (31) and `_hydrate_recurring_rows` (`recurring.py:140`) is D (29). The others are C, mostly in `web/routers/recurring.py`, `web/charts.py` and `web/auth_cookies.py:safe_next`. Maintainability index: every module is A except `web/routers/recurring.py`, B (17.61). Xenon reports 33 violations (all absolute-rank).

**Sizes** (`sizes.txt`; AST based; feeds B). 120 files, 22254 lines. Files over 800 lines: `web/routers/recurring.py` 1115, `services/forecast.py` 978. 14 files are 400 to 800 lines (largest: `routers/auth.py` 760, `services/recurring.py` 696, `services/budget.py` 664, `web/charts.py` 601, `services/recurring_formula.py` 596, `routers/planned.py` 586). The function list (functions over 50 lines, with count) and per-package line totals are in the file.

**Python clones** (`pylint-duplicate.txt`; `pylint duplicate-code`, min 6 lines; feeds A). 19 R0801 "similar lines" blocks. Score 9.98/10. The head of the file shows a repeated `write_audit(...)` call shape in `services/reauth.py` and its sibling. Clones are mostly boilerplate; the FX duplication from Track A is semantic, not textual, so lexical clones will under-report it.

**Template, CSS and JS clones** (`jscpd.txt`; `jscpd --min-lines 8 --min-tokens 50` over `web/templates` + `web/static`, vendor/tailwind/fonts excluded; feeds E). 17 clones, 270 duplicated lines of 12740 (2.12%): markup 10 clones (3.15%), css 5 (1.09%), javascript 2 (1.55%). Example: `partials/recurring/_form.html` clones itself within the file.

**Dead code** (`vulture.txt`, `unused-templates.txt`, `unused-css.txt`; `vulture src --min-confidence 60`; feeds G). Vulture: 172 findings (97 functions, 57 variables, 14 methods, 3 attributes, 1 property), nearly all 60% confidence and dominated by FastAPI route handlers, pydantic settings fields and `@field_validator` methods that vulture cannot see as used. No whitelist pass was done; Track G triages. Unused templates: 16 of 111 template files are not referenced by path from any `src/*.py` or template (example candidates: `budget/manage.html`, `categories/index.html`, `planned/index.html`, `recurring/index.html`, `transactions/index.html`, `partials/_money.html`, `partials/_pagination.html`, `partials/_cheatsheet.html`, `partials/_direction_badge.html`, `settings/_fx.html`, `settings/_prefs.html`; the list also includes `.gitkeep`). Dynamic template names may give false positives. Unused CSS: 132 of 658 class selectors in the hand-written CSS are not referenced as a token in templates, Python or JS: `app.css` 88 of 210, `rising-dough.css` 43 of 369, `auth.css` 1 of 30. Stylelint does not detect unused selectors, so the cross-check was a token grep only. Note that the Sourdough redesign replaces the markup and CSS (ADR-0107), so the CSS number is informational.

**Import graph** (`import-graph.txt`; `import-linter` dry-run with a contracts file kept outside the repo, plus `grimp` SCC detection over all imports including function-level ones; feeds B). 120 modules, 440 import edges. Contracts: 3 kept, 4 broken. Kept: `domain` -> `services`, `domain` -> `repositories/db/web/adapters`, `services` -> `web`. Broken: routers import repositories directly (13 router modules, 23 import lines under `web/`; `web` -> `repositories` is 37 edges), `web` imports `db` (5 edges: `app.py`, `routers/health.py`, `middleware/auth.py`, `deps.py`, `retention_task.py`), and `repositories` imports `services` (`repositories/recurring.py` imports `services.recurring.first_due_on_or_after`). One import cycle (SCC of 3 modules): `repositories.recurring` <-> `services.recurring` <-> `services.recurring_formula`. That cycle probably explains part of the PLC0415 and recurring suppressions. Edge counts per package pair are at the end of the file.

**SQL locations** (`sql-sites.txt`; scripted grep for `.execute(`, `.executemany(`, `text(`, literal SELECT/INSERT/UPDATE/DELETE outside `repositories/` and `db/migrate.py`; feeds B). 9 files and 21 hit lines, down from "about 14 files" in the 2026-11-06 grep. Pure bootstrap/pragma hits: `db/connection.py` (6 PRAGMA), `db/startup_migrate.py` (VACUUM INTO), `web/app.py`, `web/routers/health.py`, `services/users.py` (PRAGMA table_info), plus the enum-member false positive in `domain/enums.py`. Real DML/SELECT outside repositories: `services/accounts.py` (2 SELECT), `web/routers/planned.py` (SELECT from `audit_log` and an `UPDATE planned_transactions` at lines 140 to 156, a direct write from a router), `web/routers/recurring.py:501` (SELECT from `audit_log`).

**Clock call sites** (`clock-sites.txt`; scripted grep for `datetime.now`, `date.today`, `utcnow`, `time.time(`, `.now(`, `today()`, monotonic/perf counters; feeds C). 48 lines. Most files: `web/routers/recurring.py` 5, `db/startup_migrate.py` 4, `web/routers/budget.py` 4. Many are in routers, which is against the ADR-0007 centralisation.

**Type holes** (`mypy-any.txt`; `mypy --strict --warn-unreachable --any-exprs-report`; feeds C). Clean: no errors in 120 source files. Any-expression coverage overall: 96.18% (1305 `Any` expressions of 34201). Highest `Any` counts: `web.routers.recurring` 109, `repositories.recurring` 92, `cli.set_password` 9 (see the sorted top-50 in the file).

**bandit** (`bandit.txt`; `bandit -r src -ll`, plus all-severity totals; feeds D). Totals over all severities: 0 High, 53 Medium, 33 Low. By test: B608 (SQL built from strings) 51, B101 assert 3, B704 (markupsafe `Markup`) 4. The 51 B608 are the signal: they are probably f-string-composed SQL with fixed column/table fragments, but each needs an injectability check in Track D (likely 0 exploitable, but unverified here).

**pip-audit** (`pip-audit.txt`; `uv export --frozen --no-hashes` then `pip-audit -r --no-deps`; feeds D). 3 distinct advisories in 1 package, all `cryptography 48.0.1`: PYSEC-2026-3552 (fix 50.0.0), PYSEC-2026-3553 and PYSEC-2026-3554 (fix 49.0.0). Relevance depends on which `cryptography` code paths the app uses (webauthn, TLS); Track D to triage. The list in the raw file shows each twice.

**detect-secrets** (`detect-secrets.txt`; `scan --all-files` with sqlite, `.venv`, `.git`, caches and lockfiles excluded; values not recorded; feeds D). 8 raw hits in 4 files, all manually judged false positives: `.secrets.baseline` self-hit, SRI hashes in `docs/application_redesign_handoff/mockups/support.js` (3), prose in `docs/plans/v3/HANDOFF.md` (2), and the `private` provider blob in `terraform/bootstrap/terraform.tfstate:82` (already in the committed baseline). Observation for Track D: `terraform/bootstrap/terraform.tfstate` is committed (ADR-0096 decided the bootstrap state is committed). It contains no credential keys (grep for access_key/secret_key/password/token is empty), only bucket names and IDs. Not a Critical.

**semgrep** (`semgrep.txt`; `semgrep 1.99.0`, `--config p/python --config p/owasp-top-ten`, metrics off; feeds D). 223 rules on 274 git-tracked files, 0 findings. 35 files were only partially analysed due to parsing errors (HTML/JS), so this is a weak negative for templates.

**tflint** (`tflint.txt`; `tflint 0.66.0` release binary, bundled ruleset, per terraform directory, no plugin init; feeds D). Clean in all 9 directories. CI runs v0.53.0 with `--recursive --init`.

**checkov** (`checkov.txt`; `checkov 3.2.477`, `-d terraform`; feeds D). 0 passed, 0 failed, 0 skipped: after skipping `terraform/tests/render.tftest.hcl` (checkov cannot parse `.tftest.hcl`; one parsing error aborts the scan with 0 checks when it is included), the remaining resources are Scaleway/random/Tailscale types for which checkov has no policies. So the empty result is a coverage gap, not a clean bill. CI already runs Trivy config scan on terraform.

## Headline numbers vs README 2026-11-06 grep

| Metric | README (2026-11-06) | At AUDIT_SHA |
|---|---|---|
| Total `noqa` in `src` | about 118 | 126 |
| PLC0415 (import inside function) | 37 | 37 |
| PLR0917 (positional args) | 30 | 32 |
| DTZ011 (`date.today()`) | 18 | 18 |
| Clock call sites (`now()`/`today()` etc.) | about 45 | 48 (broader pattern incl. monotonic/perf counters) |
| Files with SQL outside `repositories/` | about 14 | 9 files, of which 4 are real DML or SELECT (`services/accounts.py`, `routers/planned.py`, `routers/recurring.py`; the rest is PRAGMA/bootstrap) |
| `web/routers/recurring.py` | about 1130 lines | 1115 |
| `web/routers/auth.py` | about 760 | 760 |
| `web/routers/planned.py` | about 570 | 586 |
| Files over 800 lines | not stated | 2 (`routers/recurring.py`, `services/forecast.py`) |

Largest routers: `recurring.py` 1115, `auth.py` 760, `planned.py` 586, `accounts.py` 509, `transactions.py` 507, `ledger.py` 491, `budget.py` 428.

## Pointers for later phases (not findings)

- `web/routers/recurring.py` is the hot spot on four signals: size 1115, 17 suppressions, MI rating B, and the highest `Any` count. The `repositories.recurring` <-> `services.recurring` cycle sits next to it.
- The layering contracts are the cleanest candidates for automated guards in Phase 4 (4 broken today; `repositories` -> `services` is a single edge).
- The one router-side write (`planned.py:155`) bypasses the repository layer, so check it against the soft-delete and audit rule (ADR-0019).
