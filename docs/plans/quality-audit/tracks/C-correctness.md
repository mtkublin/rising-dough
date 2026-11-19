# Track C — Correctness risks (T-Q06)

> Read-only audit. All `path:line` references are valid at `AUDIT_SHA = 9fb18cbca26ef305855efc8fc106d896edc82631` (the merge of `audit/quality` only added files under `docs/plans/quality-audit/`, `src/` is unchanged).
> Schema and rubric: [implementation_plan.md §4–§5](../implementation_plan.md). Repros and recorded output: [`../repro/C/`](../repro/C/).
> Prod DB (`data/budget.sqlite`) was never opened. Every experiment ran on `/tmp/audit-C*.sqlite`, copies of `data/demo.sqlite` migrated to head (0016), with `BUDGET_DATABASE_URL` set before the app settings were imported (each repro script refuses to run unless the URL is under `/tmp/`).

## 0. Headline

**One Critical** (C-01): reconciling an account with a user-chosen income/expense category can move the stored balance *away* from the bank figure (persisted wrong money, reachable from the UI). Reported to the operator immediately per §5.1.

| Severity | Count | Ids |
|---|---|---|
| Critical | 1 | C-01 |
| High | 6 | C-02 … C-07 |
| Medium | 10 | C-08 … C-17 |
| Low | 3 | C-18 … C-20 |

Confirmed (repro attached): C-01 to C-13, C-15, C-17 (partly), C-19. Probable (code citation only): C-14, C-16, C-20, and the Probable half of C-17. See each finding.

Query-count headline (demo data: 616 transactions, 10 accounts, 34 rules): `/accounts` issues **2,963 SQL statements** per request (950 identical account lookups), `/forecast` **2,774**, `/today` **228**, `/budget` 120, `/plan` 114, `/today/afford` 114. A trivial authenticated GET costs 4 queries (session overhead). See §7.

Things the operator must check on prod, because the audit cannot (hands-off rule): whether any account uses a zero-decimal currency (JPY/KRW; C-03 shows it 100x too small on `/today`), whether any account is not in the base currency (C-02/C-04), and whether any recurring rule was created with a blank "Day of month" and a start day above 28 (C-06). Any "yes" turns the matching High into Critical today.

## 1. Coverage statement

**Read in full or in the relevant part:** `domain/money.py`; `services/fx.py`, `balance.py`, `reconciliation.py`, `_promotion.py`, `retention.py`; `services/recurring.py` (cadence helpers, promote, skip, advance), `services/planned.py` (promote, batch promote), `services/budget.py` (converters, committed, month_summary), `services/today.py` (rounding helper); `services/forecast.py` (FX helpers, event collection, loop structure; not the full 978 lines line by line); `repositories/_shared.py` (transaction helper, require_owned), `repositories/accounts.py` (soft_delete), `planned.py` (stamp, recently deleted), `retention.py`; `web/today_data.py`, `web/routers/{today,budget,plan,forecast,accounts,ledger,planned}.py` (clock, parsing, fallbacks), `web/retention_task.py`, `web/routers/health.py` (except blocks), `db/migrate.py` (hooks and except blocks), `db/retention.py`, `web/app.py` (router registration, middleware order), templates that format money (`today/`, `ledger/`, `plan/`). Docker/compose/cloud-init for the host timezone.

**Grep-swept only (not read in depth):** `services/analytics.py`, `income.py`, `upcoming.py`, `account_planned.py`, `fortune.py`, `export.py`, `recurring_formula.py` beyond the preview path, `web/charts.py`, `web/routers/recurring.py` beyond the clock/parsing sites. Duplicated-logic questions between these belong to Track A.

**Checklist items applied:** time (§2), silent failures (§3), arithmetic (§4), boundaries (§5), concurrency (§6), performance (§7). ADRs 0006, 0007, 0008, 0015, 0038 read; ADR-0041/0045/0095 cited where touched.

**Skipped or not verifiable:** (1) whether the production image really contains `/usr/share/zoneinfo/Europe/Warsaw` (no Docker run; see Q-1). (2) A real-clock midnight run (clock behaviour shown with `TZ=` subprocesses instead of a frozen server). (3) Timings are indicative only: other agents were loading the machine, so counts are the signal, milliseconds are not. (4) No multi-process write-load test; the concurrency repro is a forced two-thread interleaving.

## 2. Clock call sites

### 2.1 Host timezone assumption

- `docker-compose.yml:45` (prod-sim) and `terraform/cloud-init/compose/docker-compose.yml.tpl:31` set `TZ: "Europe/Warsaw"` on the app container. The Dockerfile sets no `TZ` and installs no `tzdata` (it relies on the Debian slim base; `Dockerfile:46-52`).
- Consequence: every naive `date.today()` returns the **Warsaw** date in prod because of an environment variable, not because of `settings.display_timezone` (`config.py:47`, default `Europe/Warsaw`, validated at `config.py:150`). If the zone database is missing from the image, glibc silently falls back to UTC (Q-1). The two settings can also diverge by configuration: changing `BUDGET_DISPLAY_TIMEZONE` moves nine call sites and leaves eighteen where they were.
- CI and any non-Warsaw developer machine run on UTC or the local zone; the visual suite freezes the clock at 10:00 UTC (`tests/visual/frozen_server.py:23`), which is the one hour of the day on which the two notions of "today" can never disagree, so the divergence window is not exercised anywhere.
- **Midnight window:** a Warsaw date change happens at 23:00 UTC (CET, winter) or 22:00 UTC (CEST, summer). On a UTC-zoned process a naive `date.today()` lags the display zone by one day for 1 h (winter) or 2 h (summer) every night. Shown in `repro/C/repro_clock.py` (K1): at 22:30Z on 30 June, `TZ=UTC` gives 2026-06-30, `TZ=Europe/Warsaw` and the display zone give 2026-07-01. Within one request the router even mixes both: `web/routers/budget.py:81` (`_year_month`, naive) and `:126` (`today`, display zone) feed the same page.
- Tests that cannot freeze time: 23 sites in `tests/` call the real `date.today()` / `datetime.now()`; no `freezegun`/`time-machine` is installed. Production code that has **no injectable clock at all** (a test can only freeze it by replacing the `datetime` module in `sys.modules`, as `frozen_server.py` does): `repositories/recurring.py:227` (`create_rule` seeds `next_due`; `tests/unit/services/test_upcoming.py:5` documents the workaround), `db/migrate.py:155`, `services/planned.py:86`, and the five `date.today()` calls in `web/routers/recurring.py`.

### 2.2 Classification

Legend: **(a)** UTC timestamp for the DB or an epoch/duration; **(b)** "today" in the display timezone (correct per ADR-0007); **(c)** naive `date.today()` that is right only because the process TZ happens to equal the display zone (latent wrong; the window is in 2.1); **(c!)** wrong in its own right.

| Site | Call | Class | Note |
|---|---|---|---|
| `db/migrate.py:155` | `dt.date.today()` | (c) | backfill anchor for `next_due`; runs once per migration, harmless in practice |
| `db/migrate.py:188-189` | `now(UTC)` | (a) | stub rule timestamps for the backfill |
| `db/retention.py:21` | `now(UTC)` | (a) | |
| `db/startup_migrate.py:125,138,139,147` | `_utcnow()` | (a) | file-age arithmetic, injectable (`now` parameter) |
| `repositories/_shared.py:35` | `now(UTC).strftime(...%f)` | (a) | microsecond precision; SQL defaults use millisecond (C-19) |
| `repositories/recurring.py:147-148` | `now(UTC)` | (a) | stub only |
| `repositories/recurring.py:227` | `dt.date.today()` | (c) | `create_rule` -> initial `next_due`; not injectable |
| `repositories/sessions.py:83` | `now(UTC)` | (a) | injectable |
| `repositories/webauthn.py:164` | `now(UTC)` | (a) | injectable |
| `services/balance.py:210` | `dt.date.today()` | (c) | default for `balance_series(today=None)`; the router passes nothing (`web/routers/accounts.py:70`) |
| `services/budget.py:69` | `dt.date.today()` | (c) | default for `base_amount_converter(today=None)` |
| `services/planned.py:86` | `dt.date.today()` | (c) | default window; callers that matter inject |
| `services/recurring.py:249` | `now(UTC)` | (a) | stub only |
| `web/auth_cookies.py:68,140,184` | `now(UTC)`, `time.time()` | (a) | expiry maths, injectable `now` |
| `web/deps.py:99`, `web/routers/auth.py:96` | `clock() or now(UTC)` | (a) | the one real injectable clock in the app |
| `web/routers/health.py:95` | `now(UTC)` | (a) | |
| `web/routers/accounts.py:46` | `date.today()` (`_today`) | (c) | used for reconcile date and planned totals |
| `web/routers/budget.py:81` | `date.today()` | (c) | `_year_month`: fiscal month for the landing page |
| `web/routers/budget.py:126,156,183` | `now(ZoneInfo(display_timezone)).date()` | (b) | correct |
| `web/routers/forecast.py:48` | `date.today()` | (c) | forecast day 0 and FX date |
| `web/routers/ledger.py:292` | `date.today()` | (c) | planned-window filter |
| `web/routers/ledger.py:338,433` | `date.today()` | (c) | overdue chip maths |
| `web/routers/plan.py:76,272` | `now(ZoneInfo(...)).date()` | (b) | correct |
| `web/routers/planned.py:80` | `date.today()` | (c) | |
| `web/routers/planned.py:575`, `web/routers/transactions.py:494` | `now(UTC).strftime("%Y%m%d")` | (a) | export file name stamp; UTC date in a user-facing file name (cosmetic) |
| `web/routers/recurring.py:338,694` | `dt.date.today()` | (c) | row hydration (overdue state) |
| `web/routers/recurring.py:353` | `dt.date.today()` | (c) | `initial_active` for a new rule |
| `web/routers/recurring.py:435` | `dt.date.today()` | (c) | **batch promote due**: `next_due <= today`; at the window the nightly-due rules are not promoted |
| `web/routers/recurring.py:580` | `dt.date.today()` | (c) | formula preview month |
| `web/routers/today.py:48,109,160` | `now(ZoneInfo(...)).date()` | (b) | correct |
| `web/templating.py:192` | `now(tz).date()` | (b) | `today_local()` Jinja global |
| `web/today_data.py:123` | `date.today()` | (c) | FX **rate date** for the fortune conversion |
| SQL `strftime('%Y-%m-%dT%H:%M:%fZ','now')` (35 sites: `created_at`/`updated_at`/`deleted_at`/`fetched_at` defaults and updates in every repository, `web/routers/planned.py:157`, migrations) | | (a) | UTC, millisecond precision |
| SQL `datetime('now', ?)` at `repositories/planned.py:254`, `categories.py:56`, `transactions.py:266` | | (c!) | compares the stored `...T...Z` text with a `YYYY-MM-DD HH:MM:SS` cutoff: `'T'` sorts after `' '`, so the "last 90 days" window is up to 24 h too wide (C-19, repro K2) |
| SQL `CURRENT_TIMESTAMP`, `date('now')`, `CURRENT_DATE` | none | n/a | not used |

Totals: 18 naive `date.today()` (matches the 18 DTZ011 suppressions), 9 display-zone `now(ZoneInfo)`, 12 UTC-timestamp sites in Python, plus 35 SQL `'now'` sites and 3 `datetime('now', ?)`.

Mitigation for the whole table: see C-08 (one `clock` module).

## 3. Silent failures

Searched: every `except` in `src` (31 hits; 3 are BLE001 in `ruff-all.txt`), every `contextlib.suppress`, `.get(x, 0)`, `or 0`, and rate/amount fallbacks.

| Site | Behaviour | Class |
|---|---|---|
| `web/today_data.py:126-129` | `FxUnavailableError` -> `rates[ccy] = Decimal("1")`; fortune adds foreign amounts as if they were base currency | **wrong-number** (C-02) |
| `services/budget.py:75-83` (`base_amount_converter`) | missing rate -> native amount, log warning only; feeds "committed" | **wrong-number** (C-02) |
| `services/budget.py:106-114` (`base_txn_converter`) | missing rate -> native amount; feeds "spent", averages | **wrong-number** (C-02) |
| `web/routers/ledger.py:279-282` | missing rate -> day net `None` (blank) | acceptable (visible gap, not a number) |
| `services/forecast.py:211-217` `_collect_fx_rates` | no catch -> `/forecast` HTTP 500 | acceptable-failure, but inconsistent with the three above (C-02) |
| `services/fx.py:105-109` | any HTTP/parse error -> stale cached rate with a log warning, stale rate not persisted, remote retried on every render | acceptable per ADR-0006, but not surfaced to the user (C-17) |
| `services/budget.py:78,109` `ccy_by_account.get(id, base)` | unknown account treated as base currency | acceptable (map built with `include_deleted=True`) |
| `web/routers/ledger.py:356,410`, `:355` | `effective_amount_minor or 0`, `amount_minor or 0` | wrong-number only in combination with C-04 (mixed currencies); otherwise acceptable |
| `services/budget.py:488,520-524,544`; `services/fortune.py:39-50`; `web/today_data.py:117`; `services/forecast.py:610,874`; `services/account_planned.py:126,139`; `services/ledger_totals.py:50` | `.get(key, 0)` / `or 0` as accumulators or "no budget -> 0" | acceptable (legitimate zero; `None` vs `0` budgets are distinguished before the `or 0`) |
| `web/routers/plan.py:188` | `cells[i].amount_minor or 0` for column totals | acceptable |
| `web/routers/accounts.py:400,481` | `credit_limit_minor or 0` | acceptable (guarded by `_uses_available`, which needs a truthy limit) |
| `repositories/*:` `int(cursor.lastrowid or 0)` (13 sites) | id 0 on a failed insert would be an invalid id | acceptable (INSERT raises before) |
| `web/routers/accounts.py:491` `contextlib.suppress(NoAdjustmentNeededError)` | zero delta is not an error | acceptable |
| `services/reconciliation.py:112` | `abs(delta)` regardless of chosen category sign | **wrong-number** (C-01) |
| `web/routers/{ledger,transactions,recurring,budget,planned}.py` `except (TypeError, ValueError)` (8 sites) | invalid input -> default or 422 | acceptable; the unguarded siblings are C-10 |
| `web/routers/today.py:136-139` | `float()` parse -> 422 on `ValueError` only | NaN/inf escape as 500 (C-10) |
| `web/retention_task.py:28`, `db/retention.py:31` | broad `except Exception`, log + continue / exit 1 | acceptable (documented non-fatal; error logged with type) |
| `web/routers/health.py:57,65` | broad `except` -> 503 with reason | acceptable |
| `repositories/_shared.py:130`, `db/migrate.py:210,251,332`, `db/startup_migrate.py:183` | `except Exception: ROLLBACK; raise` | acceptable (re-raise) |
| `web/app.py:243` `except ImportError: continue` | a router that fails to import is silently skipped | silent-failure of structure, not money (C-20) |
| `web/routers/planned.py:140-157` undo | `if row is None ...: continue` skips planned rows without an audit predecessor | probable wrong-state (C-16) |

No `except: pass`, no bare `except:`, and no swallowed exception on a path that writes money was found.

## 4. Arithmetic

- **Float in money.** No float arithmetic is stored. Floats appear in (1) `web/routers/today.py:138-141` (`float(raw)` then `round(major * 100)`: afford input; NaN/inf crash, JPY-class ignored, binary-float half cases such as `1.005` -> 100 not 101), (2) chart feeds `web/routers/forecast.py:31,57`, `plan.py:36,48-56`, `services/forecast.py:956` (`/ 100.0`), (3) templates dividing by `100.0` (C-03). Display-only except (1).
- **Rounding modes in use:** `ROUND_HALF_UP` for user input (`domain/money.py:206`) and for formula coefficients/results (`services/recurring_formula.py:68,135`); `ROUND_HALF_EVEN` for FX (`services/fx.py:142,164`, three more private copies of the same conversion: `web/today_data.py:103`, `services/forecast.py:240`, and the inline copies in `forecast.py:412`), averages (`services/balance.py:118`, `budget.py:243`, `analytics.py:141`) and per-day figures (`budget.py:586`, `today.py:50`); Python `round()` on a float (half-even on the binary value) for afford; floor division `//` in `web/routers/ledger.py:363` (monthly equivalent of quarterly/yearly rules) and `web/today_data.py:157` (pace). Defensible individually, but there is no single documented policy (C-18). `domain/money.py:201` docstring calls HALF_UP "banker's-safe", which it is not.
- **Negative adjustment division:** `reconciliation.py` never divides a signed amount. Averages are taken over `abs`/positive legs (`balance.py:140-146`). `ledger.py:363` floors a positive amount. No negative integer division bug found.
- **Currency exponent:** table at `domain/money.py:14-23` lists eight currencies; everything else defaults to 2. ISO-4217 zero-decimal currencies in the offered list (VND, CLP, ISK, UGX, PYG, XAF, XOF, XPF, KMF, DJF, GNF, RWF, VUV ...) and three-decimal ones (KWD, BHD, JOD, OMR, TND, IQD, LYD) are therefore stored with the wrong scale (repro P3). `HUF: 2` is ISO-correct. Conversion is internally consistent (both sides use `currency_decimals`), so the damage is display and entry scale (C-15). The T-JPY class itself is handled in `money`/`format_money` and the `money` Jinja filter, but not in `/ 100.0` template and chart code (C-03).
- **Parsing:** `parse_amount_str` (`domain/money.py:210`) accepts `1e3` (1000.00), `1_000`, non-ASCII digits (`١٢٣`); `1e30` passes parsing then raises in `to_minor_units` (repro P1); the reconcile route calls a bare `Decimal(...)` (`web/routers/accounts.py:466-481`) and crashes on `NaN`/`Infinity`/`1e999` (C-10).
- **Overflow:** minor amounts above 2^63 raise `OverflowError` at the SQLite boundary (HTTP 500), not a validation error.

## 5. Boundaries

Pure-function repro: `repro/C/repro_recurrence_boundaries.py`. Input repro: `repro_input_boundaries.py`.

| Boundary | Result |
|---|---|
| End-of-month clamp, schedule from `generate_occurrences` | Correct: 31 Jan -> 28 Feb -> 31 Mar -> 30 Apr (`services/recurring.py:82-89`). |
| End-of-month clamp, **after promote** | **Wrong** when `day_of_month` is blank: next_due walks 28 Feb -> 28 Mar -> 28 Apr... (C-06). |
| Feb-29 yearly | Schedule recovers (2028-02-29, 2029-02-28, ..., 2032-02-29); after promotes `next_due` stays on the 28th forever (C-06). |
| `day_of_month` < start day | Occurrences emitted before `start_date` (C-13). |
| Inclusive/exclusive ranges | `list_filtered` is inclusive on both ends (`repositories/transactions.py:76-84`, `planned.py:74-79`); `committed_*` is documented half-open `[start, end)` and converts with `end - 1 day` (`services/budget.py:262-271`); consistent. `generate_occurrences` is inclusive both ends. |
| Empty month / account with no transactions | `_mean_minor` returns 0 for count 0 (`budget.py:241`), `derive_balance` returns the opening balance, `balance_series` works; `days_until_next_income = max(..., 1)` (`budget.py:575`) means "payday today" divides the whole remainder by 1 day (design choice, Q-3). |
| First/last day of period | `fiscal_month_for` uses the latest anchor income `<= today` (`budget.py:388-405`). A future-dated income row is correctly ignored. |
| Future-dated transactions | `derive_balance(as_of=None)` includes them, `balance_series` and the forecast day 0 use `as_of=today` (C-14). |
| `?month=13`, `?year=0`, `?month=abc` on `/budget` | HTTP 500 (C-10); `/plan` handles the same inputs gracefully (`plan.py:84-92`). |
| Soft-deleted account/category still referenced | Fortune silently drops the balance; rules/planned on it stay live and promotable (C-05). `require_owned` explicitly leaves liveness to services (`repositories/_shared.py:199`), and the services do not check it. |
| Closed/soft-deleted category in budgets | Lines list live categories only (`categories_repo.list_all` default); history converters use `include_deleted=True`. Consistent. |
| Leap-day input date `2026-02-30` on `/ledger` | Handled (HTTP 200). |
| Ledger paging | `page=0`, `page=-1`, `page_size=0`, `page_size=1000000` all return 200; the last is unbounded (C-12). |

## 6. Concurrency

- **Deployment shape:** one uvicorn process; sync endpoints run in the threadpool, each request opening its own connection (`web/deps.py:39`). WAL, `busy_timeout=5000`, `synchronous=NORMAL`, `wal_autocheckpoint=0` for Litestream (`db/connection.py:40-55`).
- **Deferred `BEGIN`:** `repositories/_shared.py:124` issues plain `BEGIN`. A transaction that reads, and then writes after another writer committed in between, fails immediately with `database is locked` (SQLITE_BUSY_SNAPSHOT); `busy_timeout` does not apply to that upgrade. Reproduced with two threads in `repro_concurrency.py` (C-09).
- **Read-modify-write outside the transaction:** `promote_to_actual` (`services/planned.py:149-193`) checks `promoted_to_txn_id is None` and `promote_recurring` (`services/recurring.py:356-500`) reads `next_due`, both before `with db_transaction`. There is no unique index on `promoted_from_planned_id` or on `(promoted_from_recurring_rule_id, promoted_from_recurring_date)` (`migrations/0012_multi_user.sql:219`, a plain index) and the stamp/advance UPDATEs have no compare-and-set (`repositories/planned.py:296`, `recurring.py:281`). In the forced interleaving the second request fails with `database is locked`; nothing in the code, however, prevents a duplicate if the second request did not read inside its transaction first. The protection is an accident of the deferred-begin failure (C-09).
- **Per-request writes:** every authenticated request ends with `UPDATE sessions SET last_seen_at ...` (`repositories/sessions.py:248`, seen in the trace: 4 queries per trivial GET). It is autocommit, so `busy_timeout` applies, but it serialises writers per page view and is replicated by Litestream (C-11).
- **Retention vs requests:** `db/retention.py` runs at container start and daily in a thread (`web/retention_task.py:23-31`). Both statements are table-wide and non-sargable (`WHERE datetime(changed_at) < datetime(?)`, `repositories/retention.py:26,37`; plan: `SCAN audit_log`), so on a large audit log the single write lock is held for the whole scan while requests wait up to 5 s (C-11). No data race: they are separate autocommit statements and idempotent.
- **Batch undo** (`web/routers/planned.py:133-157`) reads the audit log and writes inside a transaction; see C-16 for the logic risk.

## 7. Query counts per route

Method: `repro/C/query_counts.py`. It patches `sqlite3.connect` to attach `set_trace_callback`, logs in with `tests.auth_support.login_cookie`, requests every GET route of every router (path ids substituted from the DB) with `follow_redirects=False`, and counts statements excluding `PRAGMA`/`BEGIN`/`COMMIT`. Output: `repro/C/query_counts.out`. DB: demo copy, 616 transactions, 10 accounts, 34 rules, 2 planned rows. Every authenticated request includes **4** session/user queries (one is a write, section 6). Milliseconds are noisy (shared machine) and given for ranking only.

| Route | Status | Queries | Max identical | Verdict |
|---|---|---|---|---|
| `/accounts` | 200 | **2,963** | 950 | N+1: `balance_series` calls `derive_balance` once per day for 90 days per account; each call is 3-4 queries (account, all categories, all account txns). C-07 |
| `/forecast`, `/forecast/view` | 200 | **2,774** | 493 | N+1: `list_rules`/`list_overrides` per rule inside three collectors (`services/forecast.py:271-274,380-386,756-759`), `resolve_budget` (3 queries) per category per month (`:461,696`). C-07 |
| `/today` | 200 | 228 | 71 | repeated override lookups per rule/occurrence |
| `/budget` | 200 | 120 | 33 | same |
| `/plan` | 200 | 114 | 33 | same |
| `/today/afford`, `/afford` | 200 | 114 | 33 | same; an HTMX preview fired on `input` events |
| `/today/upcoming` | 200 | 56 | 38 | same |
| `/ledger` | 200 | 13 | 2 | but `_tab_counts` loads every transaction into Python to `len()` it (`web/routers/ledger.py:383`, C-12) |
| `/plan/analytics` | 200 | 12 | 4 | |
| `/accounts/1/reconcile` | 200 | 11 | 2 | |
| all other GETs (forms, fragments, settings, health) | 200/30x/404 | 4-9 | <=2 | fine; 404s are admin-only routes for the non-admin demo user |

Index check (`repro/C/explain_plans.out`, scratch DB): no index leads with `user_id` on `transactions`, `planned_transactions`, `audit_log`, `recurring_rules` (the only `user_id`-leading indexes are the partial unique ones on accounts/categories and `ix_sessions_user`). `transactions` list queries use `ix_transactions_live (operation_date) WHERE deleted_at IS NULL`, which spans all users; `planned pending`, `audit_log by user`, `audit_log retention scrub` and `txn recently deleted` do full `SCAN`s. `fx_rates`, `budget_*`, per-entity audit lookups are indexed. With one user this is invisible; with N users each query reads N users' rows (C-11).

Unbounded: `TransactionFilter.limit` defaults to `None` (`domain/transactions.py:91`) and all services aggregate in Python (ADR-0081 moves more of it there); `/ledger?page_size=1000000` is accepted (C-12).

## 8. Findings

Fields follow §4. "Effort": S < ½ day, M <= 2 days, L > 2 days.

### C-01 — Reconcile with a chosen income/expense category stores an adjustment of the wrong sign
- **Severity / Confidence:** Critical / Confirmed
- **Track / root cause:** C / `missing-invariant-test`, `money-arith`
- **Location(s):** `services/reconciliation.py:99-112` (and the docstring contract at `:80-87`); entry point `web/routers/accounts.py:481-492`; options offered by `web/templates/partials/accounts/_reconcile_modal.html:104-109`.
- **Description:** `reconcile()` computes `delta = actual - derived` and, for a user-chosen category, stores `abs(delta)` as `amount` (line 112). The sign then comes from the category: an expense category subtracts, an income category adds. If the direction does not match the sign of `delta`, the transaction moves the derived balance away from the figure the user just typed. The docstring promises "the adjustment amount sign is coerced to match the chosen category direction so `derive_balance` still matches the actual balance"; no coercion or validation exists. The modal lists every non-system category with no sign filter, so the mismatch is one click away.
- **Evidence:** `repro/C/repro_reconcile_and_parse.py` (B1, B2): account derived 368,581 minor, bank says +10,000; with `Groceries` (expense) the stored amount is 10,000 and the balance becomes 358,581 instead of 378,581. With `Salary` (income) and a -5,000 delta the balance rises to 363,581 instead of 353,581. Output in `repro_reconcile_and_parse.out`.
- **Impact:** A reconciled account shows a balance that differs from the real one by `2 * |delta|`, persists in the ledger, and feeds fortune, forecast and budget "spent". The user believes the account is reconciled.
- **Mitigation:** In `services/reconciliation.reconcile`, raise a validation error (new `CategoryDirectionMismatchError`, mapped to 422 by the route) unless `category.direction is ADJUSTMENT`, or (`INCOME` and `delta > 0`), or (`EXPENSE` and `delta < 0`); add a post-condition `assert derive_balance == actual` in the unit test. Restrict the modal's options to the matching sign using the same predicate (a service helper `categories_valid_for_delta`).
- **Alternatives:** Remove the "Record as" selector (F-03) and always use the Reconciliation system category (simplest; loses the feature).
- **Effort:** S
- **Related:** ADR-0008, ADR-0011; Track F (a differential test: `derive_balance == actual` for every category direction).

### C-02 — A missing FX rate silently becomes rate 1; three call sites, three different fallbacks
- **Severity / Confidence:** High (Critical if prod has a non-base account and a cache gap) / Confirmed
- **Track / root cause:** C / `silent-fallback` (also Track A `duplicate-logic`)
- **Location(s):** `web/today_data.py:126-129`; `services/budget.py:75-83`, `:106-114`; contrast `web/routers/ledger.py:279-282` (returns `None`) and `services/forecast.py:211-217` (propagates, HTTP 500); duplicated conversion code at `web/today_data.py:90-103`, `services/forecast.py:221-240`, `services/fx.py:113-164`.
- **Description:** ADR-0006 only allows "most recent known rate with a log warning". When *no* rate is cached at all, Today's fortune sets the rate to `Decimal("1")` and adds foreign minor units into the base total ("degrade gracefully; UI shows native only" - the UI does not show native only). The budget converters return the native amount, so "spent"/"committed"/averages include foreign amounts at face value. The ledger shows a blank, the forecast crashes. The only signal is a log line.
- **Evidence:** `repro/C/repro_fx_fallback.py` (F1, F2, F4) with an EUR account, empty `fx_rates`, FX API forced to raise `ConnectError`: the EUR balance enters the fortune 1:1; a 1000.00 EUR planned item converts to 100000 base minor; `/today` 200, `/budget` 200, `/plan` 200, `/forecast` 500.
- **Impact:** Wrong fortune and wrong budget numbers with no on-screen sign, exactly when the FX API is down on a fresh cache (first load of a day for a new currency, new deploy with an empty cache, a new currency account).
- **Mitigation:** One conversion entry point in `services/fx` (`to_base(conn, amount, ccy, on_date, *, policy)`), whose failure result is a typed "unconverted" value instead of a number: the totals exclude it and the view model carries an `fx_missing: set[str]` flag, rendered as a visible "no rate for EUR" banner. Delete the three private converters. Do not return `Decimal("1")` anywhere.
- **Alternatives:** Fail the page with a clear 503-style message on missing rate (consistent with the forecast, worse availability).
- **Effort:** M
- **Related:** ADR-0006, ADR-0095, Track A FX concept, C-17.

### C-03 — Money rendered with hard-coded `/ 100.0` in templates and charts (zero-decimal currencies off by 100x)
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** C / `money-arith`
- **Location(s):** `web/templates/today/index.html:32,42,52-55,89-93,100`; `today/_afford_preview.html:3,5`; `today/_upcoming.html:43`; `ledger/_table.html:69`; `ledger/index.html:98,105,114`; `plan/_budget_tab.html:6-9,36,56-57`; `plan/_analytics_bundle.html:17,43,46`; `web/routers/forecast.py:31,57`; `web/routers/plan.py:36,48-56`; `services/forecast.py:956`; `web/routers/today.py:141` (`round(major * 100)` on input).
- **Description:** The `money` / `money_num` Jinja filters and `format_money` honour `currency_decimals`, but these templates and chart feeds divide by a literal 100. For a JPY/KRW account (0 decimals) the page shows one hundredth of the value; for a JPY base currency every hero figure, chart and the afford input are off by 100x. Row `today/index.html:100` shows each account's *native* balance, so a single JPY account is enough.
- **Evidence:** `repro/C/repro_jpy_display.py`: account of 1,000,000 JPY. `/accounts` (filter) renders `1,000,000`; `/today` account row renders `10,000.00`.
- **Impact:** Wrong money on the home page for any zero- or three-decimal currency. Dormant until such an account exists (operator check, section 0).
- **Mitigation:** Route every amount through `money_num(currency)` (templates) and a single `minor_to_major(amount, currency)` helper (charts, services). Replace `_MINOR_UNITS_PER_MAJOR` and the afford parser with `parse_amount_str` + `to_minor_units(base_currency)`. Add an architecture test that rejects `/ 100` and `* 100` in `web/` and `services/`. The Sourdough redesign replaces these templates (ADR-0107), so the same rule must be in the new templates' brief; the Python half (charts, afford) survives it.
- **Effort:** S-M
- **Related:** C-15, Track E (template logic), ADR-0107, ADR-0006.

### C-04 — Ledger summary strips add raw amounts across currencies (and, for planned, across directions) under a hard-coded "PLN"
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** C / `money-arith`
- **Location(s):** `web/routers/ledger.py:343-374` (`_recurring_summary`), `:410-414` (`planned_total_minor`); labels at `web/templates/ledger/index.html:99,106,114`.
- **Description:** `monthly_in/out` sums each rule's `effective_amount_minor` (native currency of the rule's account) with no conversion and floors quarterly/yearly rules with `//` (`:363`). `planned_total_minor` sums every unpromoted planned row's positive amount regardless of direction or currency. The result is printed with the literal label `PLN`, not `base_ccy`.
- **Evidence:** `repro_fx_fallback.py` F3: planned rows of 500.00 EUR (expense), 300.00 PLN (expense) and 1,000.00 PLN (income) render as `3 items · 1,800.00 PLN`. No conversion, no direction, wrong label for a non-PLN base.
- **Impact:** A number labelled as money in the base currency that is neither a net nor a base-currency total.
- **Mitigation:** Compute both strips in a service (`services/ledger_totals.py`), converting through the single converter from C-02, signing by direction, and passing `base_ccy` to the template; show income and expense separately for planned. Replace `//` with the HALF_EVEN helper.
- **Effort:** S
- **Related:** C-02, C-03, C-18, Track A (aggregates).

### C-05 — Soft-deleting an account silently drops its balance from the fortune and leaves live rules pointing at it
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** C / `missing-invariant-test` (also Track B `repo-bypass`)
- **Location(s):** `web/routers/accounts.py:348-354`; `repositories/accounts.py:138-155`; `repositories/_shared.py:199-200`; `services/_promotion.py:41-60`; `services/recurring.py:356-500`; `web/today_data.py:112-139` (fortune uses live accounts only).
- **Description:** The delete route calls `soft_delete` with no check for a non-zero balance, live recurring rules, or unpromoted planned items on the account. `require_owned` documents that liveness is "the service layer's concern", but `validate_promotion` only looks at accounts for transit currency checks. Result: the fortune changes by the account's balance at the moment of deletion; the rules and planned items keep appearing in Upcoming/Forecast and can be promoted into the hidden account.
- **Evidence:** `repro/C/repro_deleted_refs.py`: soft-deleting an account with balance -660,115 moves the fortune by +660,115; 7 upcoming rows still reference it; `promote_recurring` creates transaction #617 on the deleted account, which `list_all()` does not show.
- **Impact:** Fortune and forecast silently change by the deleted account's balance; new transactions land on an invisible account and keep affecting balance-derived views for any consumer that includes deleted accounts (the budget converters do).
- **Mitigation:** In `services/accounts` add `archive_account()` that refuses (typed error -> 409 with a message) when balance != 0 or live rules/planned reference it, or offers to deactivate them in the same transaction; add liveness checks for account and category in `validate_promotion` and `transactions.create` at service level.
- **Effort:** M
- **Related:** ADR-0019, ADR-0022, ADR-0038; Track B.

### C-06 — Recurring `next_due` drifts off the schedule after a clamped month when `day_of_month` is blank
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** C / `missing-invariant-test`
- **Location(s):** `services/recurring.py:272-306` (`advance_next_due` builds a stub whose `start_date` is `from_date`, so `anchor_day = rule.day_of_month or start.day` at `:130` becomes `from_date.day`); callers `:464-470`, `:527-533`; the form field is optional (`web/templates/partials/recurring/_form.html:196-200`, `web/routers/recurring.py:370`).
- **Description:** `generate_occurrences` anchors on the rule's real `start_date`; `advance_next_due` anchors on the date it was handed. For a rule starting 31 Jan with a blank day, the schedule is 31 Jan, 28 Feb, 31 Mar, 30 Apr, but after promoting 28 Feb `next_due` becomes 28 Mar and stays on the 28th. A yearly 29 Feb rule never returns to the 29th (2032). Because promotion stamps the promoted date, the canonical date (31 Mar) is not in the dedup keys, so `committed_by_category` (`services/budget.py:310-325`, generator anchored on `start_date`) counts the same month twice (once as spent on the 28th, once as committed on the 31st).
- **Evidence:** `repro/C/repro_recurrence_boundaries.py` R1: canonical `[..., 2026-03-31, 2026-04-30, ...]`, walk `[2026-02-28, 2026-03-28, 2026-04-28, ...]`. R2: Feb-29 rule walk stays on 28 Feb through 2033.
- **Impact:** Wrong due dates, an overdue/due-today flag on the wrong day, and a double-counted month in "committed" for end-of-month rules (rent, salary on the 31st) created without a day-of-month.
- **Mitigation:** Persist the anchor: set `day_of_month = start_date.day` on create when blank (service-level default plus a one-off data fix in the remediation task), and make `advance_next_due` take the rule (so it anchors on `rule.start_date`) instead of a `from_date` stub. Add a property test: promoting repeatedly yields exactly `generate_occurrences`.
- **Effort:** S-M
- **Related:** ADR-0038, ADR-0087; C-13.

### C-07 — N+1 query storms on `/accounts`, `/forecast`, `/today`, `/budget`, `/plan`
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** C / `missing-invariant-test` (no query-budget test)
- **Location(s):** `services/balance.py:191-217` (90 `derive_balance` calls per account) with `derive_balance` at `:87-107` (3 queries each: account, all categories, all account transactions); `web/routers/accounts.py:68-70`; `services/forecast.py:271-274,380-386,456-461,690-696,756-759`; `services/recurring.py:641-657` and `linked_occurrence_keys` (`:660`) called per rule.
- **Description:** See section 7. `/accounts` = 2,963 statements (941 of them re-read every transaction of an account, 941 re-list all categories); `/forecast` = 2,774 (493 per-rule override reads, 492 per-rule rule reads, 406+356+354 budget-tier lookups); `/today` = 228. All grow linearly with accounts x days or rules x months x categories; with several users the per-user cost is unchanged but the shared write lock (section 6) and the missing user indexes (C-11) multiply it.
- **Evidence:** `repro/C/query_counts.out` and the top-statement listing printed by `query_counts.py /accounts /forecast /today`.
- **Impact:** Multi-second page loads on 616 transactions (12 s for `/accounts` on a loaded machine, counts are the reliable figure); degrades with data growth; every query also holds a connection in the threadpool.
- **Mitigation:** (1) `balance.balance_series`: one query for the account's transactions, then a running sum in Python (the existing docstring already says to do so); (2) in forecast/today/budget, load rules, overrides, planned and budget tiers once per request into dicts and pass them down. Add a pytest query-budget helper (`assert_max_queries(route, n)`) for `/accounts`, `/today`, `/forecast`, `/budget`, `/plan`.
- **Effort:** M
- **Related:** ADR-0081 (aggregation in Python), Track B, C-12.

### C-08 — Two sources of "today": the process timezone and `display_timezone`
- **Severity / Confidence:** Medium / Confirmed (mechanism) - impact depends on the host zone
- **Track / root cause:** C / `clock`
- **Location(s):** the 18 `date.today()` sites and 9 display-zone sites listed in section 2.2; host assumption `docker-compose.yml:45`, `terraform/cloud-init/compose/docker-compose.yml.tpl:31`; `Dockerfile` (no `TZ`, no tzdata install); `web/routers/budget.py:81` vs `:126`.
- **Description:** ADR-0007 intends the display zone for "today". Half the code uses it and half relies on `TZ=Europe/Warsaw` on the container. Correct in prod only while that env var and the zone database exist, and while `display_timezone` is not changed. In the nightly window (1 h winter, 2 h summer) any non-Warsaw process disagrees by one day: batch-promote due (`recurring.py:435`), fiscal month (`budget.py:81`), reconcile date (`accounts.py:46`), the FX rate date for the fortune (`today_data.py:123`), recurring `initial_active` and `next_due` seeding (`repositories/recurring.py:227`). Tests run on the CI zone and the visual suite freezes at 10:00 UTC, so no test exercises it.
- **Evidence:** `repro/C/repro_clock.py` K1.
- **Impact:** For one to two hours a day on a UTC host: wrong month on the Budget landing page, rules due "today" not offered, reconciliation dated yesterday. In prod today: none, as long as the TZ env var is honoured.
- **Mitigation:** One module `budget_planner/clock.py` with `utc_now()`, `today_local(settings)` and an injectable override (a `ContextVar`) used by tests and the visual suite; replace the 27 sites; ban `date.today`/`datetime.now` outside it with ruff `TID251` banned-api (this removes the 18 `DTZ011` suppressions). Keep `TZ` in compose for log timestamps only.
- **Effort:** M
- **Related:** ADR-0007, implementation_plan §7.2 (`clock` control), Track F (frozen-clock tests).

### C-09 — Concurrent writers fail with `database is locked`; promote is read-then-write outside the transaction
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** C / `missing-invariant-test`
- **Location(s):** `repositories/_shared.py:124` (deferred `BEGIN`); `services/planned.py:149-193`; `services/recurring.py:356-500`; no unique index (`migrations/0012_multi_user.sql:219`).
- **Description:** Two requests promoting the same planned row/rule both pass the pre-checks. The loser runs a read (ownership check) and then a write inside a deferred transaction after the winner committed, which SQLite aborts with `database is locked` regardless of `busy_timeout`. The user sees HTTP 500 (`web/errors.py:156` generic handler). Duplicate transactions are prevented only by that accident, not by an invariant. With multi-user deployment (ADR-0061) and a double click or two tabs this is a real path.
- **Evidence:** `repro/C/repro_concurrency.py`: `['OperationalError: database is locked', 'ok txn_id=617']`, one linked transaction for the planned row, same for the recurring rule (`repro_concurrency.out`).
- **Impact:** Intermittent 500s on promote/save under concurrency; a latent duplicate-transaction hole if the interleaving changes.
- **Mitigation:** Use `BEGIN IMMEDIATE` in `repositories/_shared.transaction` (waits on `busy_timeout` instead of failing), move the pre-checks inside the transaction, and add compare-and-set: `UPDATE planned_transactions SET promoted_to_txn_id=? WHERE id=? AND user_id=? AND promoted_to_txn_id IS NULL` (check `rowcount`) plus a partial unique index on `transactions(promoted_from_planned_id)` and on `(promoted_from_recurring_rule_id, promoted_from_recurring_date)` where `deleted_at IS NULL`.
- **Effort:** M
- **Related:** ADR-0019, ADR-0061, Track B (transactions).

### C-10 — Boundary inputs that crash with HTTP 500 instead of 422
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** C / `missing-invariant-test` (overlaps Track D input validation)
- **Location(s):** `web/routers/budget.py:79-86` (`int(q.get("year"/"month"))` unguarded, then `date(year, month, 1)`); `web/routers/today.py:127-141` (`float("nan")`, `inf`, `1e999`); `web/routers/accounts.py:466-481` (bare `Decimal(...)` then `to_minor_units`); `domain/money.py:210-231` (accepts `1e3`, `1e30`, `_`, non-ASCII digits).
- **Evidence:** `repro/C/repro_input_boundaries.py`: `/budget?month=13|0|abc`, `year=0`, `year=10000` -> 500; `/today/afford?amount=nan|inf|1e999` -> 500; POST reconcile `NaN`, `Infinity`, `1e999` -> 500. `/plan` handles the same month inputs (`plan.py:84-92`). `repro_reconcile_and_parse.py` P1/P2 for the parser.
- **Impact:** Error pages and ERROR logs on malformed input; `/today/afford` is an HTMX preview called on each keystroke.
- **Mitigation:** One shared `parse_year_month(request, fallback)` used by `/budget` and `/plan`; make `parse_amount_str` the only amount parser (reject exponents, `NaN`/`Infinity`, non-ASCII digits, magnitude above a named `MAX_MINOR`); reconcile and afford call it.
- **Effort:** S
- **Related:** Track D (input validation), C-03.

### C-11 — No `user_id`-leading indexes on the large multi-user tables; a session write on every request
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** C / `scoping-gap` (performance side)
- **Location(s):** `migrations/0012_multi_user.sql:212-219,274-275,338`; `repositories/retention.py:26,37`; `repositories/sessions.py:248`.
- **Description:** Every query is scoped `WHERE user_id = ?` (ADR-0061) but `transactions`, `planned_transactions`, `audit_log` and `recurring_rules` have no index that starts with `user_id`; plans show `SCAN`/non-selective scans (`explain_plans.out`). With N users each page reads all users' rows and filters after the fact. The retention statements use `datetime(changed_at)` (non-sargable) and hold the write lock for a full scan. Every authenticated GET performs an `UPDATE sessions` (autocommit), replicated by Litestream.
- **Evidence:** `repro/C/explain_plans.out`; `query_counts.out` (4 queries on every route, one write).
- **Impact:** Latency and lock time grow with total data, not per-user data, as users are added.
- **Mitigation:** New migration adding `(user_id, operation_date) WHERE deleted_at IS NULL` on `transactions` and `planned_transactions`, `(user_id, id)` on `audit_log`, `(user_id, active)` on `recurring_rules`; store `changed_at` in a comparable form or add an index on it for the purge; throttle `last_seen_at` writes to once per minute.
- **Effort:** S-M
- **Related:** ADR-0061, ADR-0078 §7, C-07.

### C-12 — Unbounded queries: all-row loads for counts, balances and aggregates; unbounded page size
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** C / `missing-invariant-test`
- **Location(s):** `web/routers/ledger.py:377-390` (`len(list_filtered(... limit=None))`); `domain/transactions.py:91` (default `limit=None`); `services/balance.py:77-82` (all transactions of an account per `derive_balance`); `services/budget.py:246-250` (`_all_expense_txns`, every expense ever, per `month_summary`); `web/routers/ledger.py` `page_size` (no upper bound, `page_size=1000000` -> 200); `web/routers/health.py` `PRAGMA integrity_check` on every `/ready` probe.
- **Description:** Counts, balances and "all-time average" read every row into Python on each request. Fine at 616 rows, linear in history afterwards, and amplified by C-07.
- **Evidence:** section 7 plus `query_counts.out`; `repro_input_boundaries.out` (`page_size=1000000`).
- **Impact:** Memory and latency growth over the years of data this app is built to hold.
- **Mitigation:** `SELECT COUNT(*)` and `SELECT SUM(...)` repository functions for counts/balances/aggregates (also what ADR-0081 needs); clamp `page_size` to a named maximum; use `PRAGMA quick_check` (or a cheaper readiness probe) for `/ready`.
- **Effort:** M
- **Related:** ADR-0081, C-07, C-11.

### C-13 — Occurrences are generated before the rule's `start_date` when `day_of_month` is earlier than the start day
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** C / `missing-invariant-test`
- **Location(s):** `services/recurring.py:123,143` (`hard_start` computed, then `occ_date >= range_start` is used instead).
- **Description:** A rule with `start_date=2026-03-25`, `day_of_month=20` yields 2026-03-20 as its first occurrence, before the rule exists. `first_due_on_or_after` then seeds `next_due` in the past.
- **Evidence:** `repro_recurrence_boundaries.py` R3: `['2026-03-20', '2026-04-20', '2026-05-20']`.
- **Impact:** A phantom overdue occurrence on creation; counted in committed/forecast windows.
- **Mitigation:** Compare against `max(range_start, rule.start_date)` (`hard_start`) in the loop, or reject `day_of_month` combinations that put the first occurrence before `start_date` in the form validation.
- **Effort:** S
- **Related:** C-06.

### C-14 — "Current" balance includes future-dated transactions; forecast day 0 and sparkline do not
- **Severity / Confidence:** Medium / Probable
- **Track / root cause:** C / `missing-invariant-test` (cross-implementation; also Track A)
- **Location(s):** `services/balance.py:87-107` (`as_of_date=None` -> all), `:210-217` (`balance_series` as-of per day); `web/today_data.py:116`, `services/fortune.py:36` (latest) vs `services/forecast.py:498` (`as_of_date=today`).
- **Description:** A transaction dated next week changes the Today fortune and the account balance now, but the forecast day-0 and the last sparkline point (`as_of=today`) exclude it, so the same account shows two balances. No repro was run (needs a future-dated actual, which the form appears to allow).
- **Impact:** Two "current balances" that differ by future-dated entries.
- **Mitigation:** Decide the rule once (ADR amendment): a `balance.as_of_today(conn, user, account, today)` used by every consumer; if future-dated actuals are allowed, they stay out of "current".
- **Effort:** S-M
- **Related:** ADR-0011, ADR-0015, Track A.

### C-15 — Currency exponent table covers 8 currencies; other zero- and three-decimal ISO currencies are stored at the wrong scale
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** C / `money-arith`
- **Location(s):** `domain/money.py:14-23,190-195`; the currency picker offers all ISO codes (`:26-188`).
- **Description:** VND, CLP, ISK, UGX, PYG, XAF/XOF/XPF, KMF, DJF, GNF, RWF, VUV (0 decimals) and KWD, BHD, JOD, OMR, TND, IQD, LYD (3 decimals) default to 2. Entry, storage and FX stay self-consistent, but display and entered scale are wrong (a 1,000 VND account renders `1,000.00`, entry `1000` becomes 100,000 minor), and any future import/export with real minor units would be off.
- **Evidence:** `repro_reconcile_and_parse.out` P3.
- **Impact:** Wrong-scale display and entry for those currencies; none for PLN/EUR/USD/GBP/CHF/HUF/JPY/KRW.
- **Mitigation:** Generate the exponent table from ISO 4217 (all 180 codes) next to `ISO_4217_CURRENCIES` and add a unit test that every offered code has an explicit entry; or restrict the picker to currencies with an explicit exponent.
- **Effort:** S
- **Related:** C-03, ADR-0006, ADR-0030.

### C-16 — Batch-promote undo restores the last audit `update`, bypasses the repository, and writes no audit entry
- **Severity / Confidence:** Medium / Probable
- **Track / root cause:** C / `silent-fallback` (also Track B `repo-bypass`)
- **Location(s):** `web/routers/planned.py:133-157`.
- **Description:** For each planned id the undo takes the newest `update` row from `audit_log` and writes its `promoted_to_txn_id` back, using raw SQL in the router. If the planned row was edited after the batch (a later `update` entry whose `prev_json` already contains the new `promoted_to_txn_id`), the stale id is restored; the transaction was soft-deleted, so the planned row stays "promoted" and vanishes from Upcoming while its money is gone. A row without a matching audit entry is skipped (`continue`) silently. The audit lookup has no `user_id` filter. No audit row records the restore (ADR-0019).
- **Evidence:** code citation only (no repro; needs an edit between batch and undo).
- **Impact:** A planned item silently disappears after an undo in an uncommon sequence.
- **Mitigation:** Move to `services/planned.undo_batch_promote(conn, user_id, promotions)` taking the explicit `(planned_id, txn_id)` pairs from the request, unstamping by compare-and-set (`WHERE promoted_to_txn_id = :txn_id`) through the repository helper so the audit row is written.
- **Effort:** S
- **Related:** Track B, ADR-0019.

### C-17 — FX fetch is network I/O in the page render, retried on every request, and stale rates are never surfaced
- **Severity / Confidence:** Medium / Confirmed (code and repro F4) / Probable (latency)
- **Track / root cause:** C / `silent-fallback`
- **Location(s):** `web/today_data.py:119-130` (`httpx.Client(timeout=5.0)` per render), `web/routers/forecast.py:46-51`, `services/fx.py:96-110,146-164`.
- **Description:** `get_rate` for today's date fetches remotely on a cache miss; when the call fails, the stale rate is returned but not persisted, so the next request tries the network again (5 s timeout per currency, sequentially). `ledger.py` and the budget converters use the cache-only `convert_cached` precisely so rendering never blocks on the network; `/today` and `/forecast` do not. A stale rate carries no age indicator in the UI.
- **Evidence:** code; `repro_fx_fallback.out` F4 (different outcomes per page).
- **Impact:** Up to `5 s x currencies` of added latency per `/today` load while the FX API is down; silently stale numbers.
- **Mitigation:** Move rate fetching to a background refresh (startup and daily, alongside the retention loop) and make all page renders cache-only via `convert_cached`; return the rate's date with the value so views can flag "rate from 3 days ago".
- **Effort:** M
- **Related:** C-02, ADR-0006, ADR-0015.

### C-18 — No single rounding policy: HALF_UP, HALF_EVEN, float `round()`, and floor division are all in use
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** C / `money-arith`
- **Location(s):** `domain/money.py:198-207`; `services/recurring_formula.py:68,135`; `services/fx.py:142,164`; `services/today.py:50`; `web/routers/today.py:141`; `web/routers/ledger.py:363`; `web/today_data.py:157`; docstring at `domain/money.py:201`.
- **Description:** Each choice is individually defensible (input uses HALF_UP, derived values HALF_EVEN), but there is no documented policy, the docstring calls HALF_UP "banker's", and two sites use floor/float rounding, so the same half-minor value can round differently depending on the screen.
- **Evidence:** section 4; `repro_reconcile_and_parse.out` P4.
- **Impact:** Off-by-one-minor-unit differences between screens.
- **Mitigation:** `domain/money.py` exports `round_div(numerator, denominator)` (HALF_EVEN) and `round_scaled(Decimal)`; document the policy in ADR-0006; replace the ad-hoc `quantize` calls.
- **Effort:** S
- **Related:** Track A (aggregates), C-03.

### C-19 — Retention window and timestamp format mismatches (`T`/space, ms/us)
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** C / `clock`
- **Location(s):** `repositories/planned.py:254`, `categories.py:56`, `transactions.py:266` (`deleted_at > datetime('now', ?)`); `repositories/_shared.py:35` vs the SQL `%f` defaults.
- **Description:** `deleted_at` is stored `YYYY-MM-DDTHH:MM:SS.mmmZ`; `datetime('now','-90 days')` yields `YYYY-MM-DD HH:MM:SS`. The text comparison treats every row from the boundary date as newer ('T' > ' '), widening the "recently deleted" window by up to 24 h. Python writes microseconds (`.%fZ`), SQL writes milliseconds, so `...:00.123Z` sorts after `...:00.123456Z`.
- **Evidence:** `repro/C/repro_clock.py` K2, K3.
- **Impact:** A deleted row stays restorable up to a day longer than documented; sub-millisecond ordering is not reliable.
- **Mitigation:** Compare with `strftime('%Y-%m-%dT%H:%M:%fZ','now',?)` (same format on both sides) and use one precision (`utc_now_iso` -> milliseconds).
- **Effort:** S
- **Related:** ADR-0007, ADR-0019.

### C-20 — Router registration swallows `ImportError`
- **Severity / Confidence:** Low / Probable
- **Track / root cause:** C / `silent-fallback`
- **Location(s):** `web/app.py:238-247`.
- **Description:** A router module that fails to import (typo, missing dependency) is skipped (`# pragma: no cover`); the app starts and the routes return 404. The "iterative landing" rationale is obsolete.
- **Evidence:** code citation.
- **Impact:** A broken import removes a feature without a failed boot or a failed healthcheck.
- **Mitigation:** Import routers explicitly in `create_app` and let `ImportError` propagate.
- **Effort:** S
- **Related:** Track B.

## 9. Questions (not findings)

1. **Q-1.** Does the production image contain `/usr/share/zoneinfo/Europe/Warsaw`? If not, `TZ=Europe/Warsaw` is a silent no-op (UTC) and C-08 is live in prod, not latent. Check with `docker run --rm <image> python -c "import datetime;print(datetime.date.today(), datetime.datetime.now())"` under `TZ=Europe/Warsaw` near midnight, or `ls /usr/share/zoneinfo/Europe/Warsaw`.
2. **Q-2.** Does prod hold a JPY/KRW (or any non-2-decimal) account, a non-base account, or a recurring rule with a blank day-of-month and a start day above 28? Each would promote C-03, C-02/C-04, C-06 to Critical. Needs the operator (no prod access).
3. **Q-3.** `days_until_next_income = max(..., 1)` (`services/budget.py:575`): is dividing the whole remainder by one day on payday intended? The "average per active month" (`_active_month_counts`) skips months with no transactions at all in a category; intended?
4. **Q-4.** `spent_minor` is summed over the paycheck window `[last_anchor_date, today]` but budgets are per calendar month; is the displayed month label (fiscal month of the last paycheck) acceptable when a paycheck lands after month end (ADR-0041/0064)? No defect proven.
5. **Q-5.** Are future-dated *actual* transactions meant to be allowed (C-14)?
6. **Q-6.** `fx_rates.rate` is `TEXT`; a stored rate of `0` or a negative value would zero out or flip conversions. Is a CHECK needed (`rate > 0`)? Not reproduced.
7. **Q-7.** `forecast` budget overlay loops `resolve_budget` for every expense category and month; the cost is C-07. Whether forecast should read budgets in bulk should be settled together with Track A's budget-tier concept.
8. **Q-8.** `/accounts` sparkline last point (`as_of=today`, naive date) vs card balance (latest): is the one-day lag on a UTC host acceptable for a card?

## 10. Repro index

| File | Shows |
|---|---|
| `repro/C/query_counts.py` / `.out` | per-route SQL statement counts (section 7) |
| `repro/C/explain_plans.py` / `.out` | EXPLAIN QUERY PLAN for user-scoped filters, index list (C-11) |
| `repro/C/repro_reconcile_and_parse.py` / `.out` | C-01 (B1, B2), parsing P1-P2, exponent P3, rounding P4 (C-10, C-15, C-18) |
| `repro/C/repro_fx_fallback.py` / `.out` | C-02, C-04, C-17 |
| `repro/C/repro_jpy_display.py` / `.out` | C-03 |
| `repro/C/repro_deleted_refs.py` / `.out` | C-05 |
| `repro/C/repro_recurrence_boundaries.py` / `.out` | C-06, C-13 |
| `repro/C/repro_concurrency.py` / `.out` | C-09 |
| `repro/C/repro_input_boundaries.py` / `.out` | C-10 |
| `repro/C/repro_clock.py` / `.out` | C-08 (K1), C-19 (K2, K3) |

All scripts refuse to run unless `BUDGET_DATABASE_URL` (or the path argument) is under `/tmp/` and not `budget.sqlite`. The `.out` files are the recorded outputs at `AUDIT_SHA`. Pytest does not collect them (`testpaths = ["tests"]`; ruff and mypy exclude `docs/`).
