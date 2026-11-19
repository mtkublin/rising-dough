# Track H2: Red team, isolation between users and privilege (T-Q18/H2)

> White-box, local-only red team at `AUDIT_SHA = 9fb18cbca26ef305855efc8fc106d896edc82631`. Scratch DBs under `/tmp/audit-H2-*/` only, in-process `TestClient` on 127.0.0.1, outbound HTTP hard-disabled in the harness (`httpx.Client.send` raises). No prod, no `data/budget.sqlite`, no fixes, no test-suite runs. Repros and recorded output: `docs/plans/quality-audit/repro/H2/`.

## Critical findings

**None confirmed.** No user could read another user's data, and no non-admin gained admin. One finding needs the operator's attention first:

- **H2-01 (High, extends D-01)**: `POST /budget/preferences/income-anchor` is hard-wired to `user_id=1`. Beyond D-01 (clearing user 1's anchor) any signed-in user can also **set** user 1's anchor to any of user 1's income categories and **probe user 1's category ids and directions** through the 200 / 422 answers. It is a cross-user write plus a small cross-user read oracle. **If prod has more than one active user, treat it as Critical** (same condition as D-01). Because the instruction was "Critical: stop chaining", this was *not* chained further: nothing else in the track depends on it.

## Summary

| Severity | Count | IDs |
|---|---|---|
| Critical | 0 | none (H2-01 is conditional Critical, see above) |
| High | 1 | H2-01 |
| Medium | 2 | H2-02, H2-03 |
| Low | 2 | H2-04, H2-05 |

Everything else attempted was **clean** (section 2). The isolation model holds: every repository query carries `user_id`, child tables without a `user_id` column (`account_snapshots`, `recurring_rule_overrides`) are scoped by a join to the parent, and no operation ever moves ownership, so check-then-act races between users have no effect to exploit.

## 1. Coverage

Harness (`repro/H2/_harness.py`): migrated scratch DB, four users (1 admin ADM, 2 victim V, 3 attacker A, 4 second admin ADM2), one of each record per user, signed-in sessions with the CSRF header pre-wired. It builds on the Track D IDOR-matrix approach (same user layout, same seed shape, own copy because `idor_matrix.py` runs its whole matrix at import). The single-request IDOR matrix was **not repeated** (D: 43 path-id routes clean); H2 goes multi-step.

Code read: `web/routers/{budget,planned,recurring,settings,settings_users,forecast,plan,ledger}.py` (relevant handlers), `services/{users,preferences,recurring_formula,accounts,rate_limit}.py`, `repositories/{audit,preferences,snapshots,users}.py`, the override and `set_next_due` parts of `repositories/recurring.py`, `repositories/_shared.transaction`, `db/connection.py` pragmas, `services/fx.py` (head).

## 2. Goals attempted and results

| Goal | Result | Evidence |
|---|---|---|
| Undo/restore: A replays V's real batch payload (planned and recurring), crafted ids (negative, zero, duplicates, V's txn/planned/rule ids) | **Clean.** 204 returned, V's rows byte-identical, 0 audit rows written. Writes are `user_id`-scoped, `soft_delete` returns early on a foreign id, the `audit_log` read (no `user_id` filter) only feeds an `UPDATE ... AND user_id = ?`, and its result never reaches the response. Audit ids cannot be recycled to cross users (rows are soft-deleted only; `retention.py` never deletes audit rows). | `h2_02_undo_chain.py` |
| Undo, own-data correctness with a stale toast | **Finding H2-03** | same script |
| Formula `source_category_ids` on preview, create, update, promotion | Evaluation is **clean** (every rule list and sum is `user_id`-scoped, so V's amounts never enter A's total; no leak on 5 evaluating views). **Finding H2-02**: the save path never validates the source ids. | `h2_03_formula_foreign_sources.py` |
| Exports, HTMX fragments, search/filter, pagination, chart endpoints with V's ids | **Clean**: 2 777 requests, 33 GET routes x 24 param families x plain/HX, V's live/deleted/planned/rule rows tagged with unique sentinels and amounts, wildcard `q` (`%`, `_`), SQL-ish values, `page`/`page_size` extremes, plus combined-filter exports. 0 leaks, 0 5xx. Control: V sees the sentinel on the same route. (The bare search term echoed in the input box is excluded from "leak"; it is the caller's own input.) | `h2_06_read_sweep.py` |
| Transfers/transit, reconcile category, planned rows to V's records | Covered by D's FK-injection mode (A's session, A's path ids, V's ids in every FK form field); not re-run. Re-checked statically: `require_owned` guards `update_rule` and the create paths, `account_snapshots.create` checks the parent owner. | D `idor_matrix_output.txt` |
| Preferences chain (D-01) for a 2-user setup | **Finding H2-01** | `h2_01_anchor_oracle.py` |
| Shared/global tables writable by a non-admin | Tables without `user_id`: `account_snapshots`, `recurring_rule_overrides` (join-scoped, see above), `fx_rates` (written only from the remote rate fetch; the user controls the currency code, not the rate), `auth_rate_limit` (**H2-04**), `schema_migrations`, `users` (admin only). | `h2_05_tables_without_user_id.py`, `h2_07_...` |
| Admin: non-admin to admin by mass assignment | **Clean.** Extra `is_admin` / `role` / `user_id` fields posted to every writable form (settings users, password, accounts, categories) are ignored or 404; `is_admin` is re-read from the DB on every request. | `h2_04_admin_chain.py` (1) |
| Admin: self-delete, self-demotion, last admin | Last-admin and self-delete invariants hold (409). Minor behaviours in **H2-05**. | `h2_04_admin_chain.py` (2) |
| Admin: concurrent mutual removal of the only two admins | Invariant **holds** (1 admin remains); the loser gets an unhandled `OperationalError` ("database is locked"), see **H2-05**. | `h2_04_admin_chain.py` (3) |
| Admin audit-tail view | Verified placeholder: V's row shows `"prev":"[other-user]","new":"[other-user]"`; accepted risk per ADR-0078 §1, no payload leak. | `h2_07_...` (b) |

**Not attempted:** passkey ceremonies, forced-rotation gate and session fixation (H3); real proxy behaviour and `X-Forwarded-For` rewriting (H4, so the cross-IP variant of H2-04 stays a question); remote FX responses (no outbound traffic allowed); XSS/CSRF (D); load or timing races over real HTTP (only a deterministic barrier-forced race at the service layer); the admin password-reset takeover (accepted v3 risk, not rediscovered).

## 3. Findings

### H2-01 | High (Critical if more than one active user) | Confirmed | scoping-gap | Income-anchor endpoint is bound to user 1: cross-user write plus a category oracle

- **Location(s):** `src/budget_planner/web/routers/budget.py:375-398` (literal `1` at lines 387 and 394). Extends D-01.
- **Description:** the handler has no `current_user_id` dependency and passes the constant `1` to `set_income_anchor_category_id`. The service then validates the category against user 1. Consequences for any other signed-in user: (a) can clear user 1's anchor (D-01); (b) can **set** it to any of user 1's income categories, by guessing small integer ids; (c) the answer discloses user 1's categories: `200 ok` means "live income category of user 1", `422 "category N direction=expense; ..."` means "exists, expense", `422 "not found or soft-deleted"` means no. (d) the user's own anchor cannot be set at all (422 for their own income category), so the Settings control is dead for every non-first user. Violates ADR-0061 §5.
- **Evidence:** `repro/H2/h2_01_anchor_oracle.py`, output `h2_01_anchor_oracle_output.txt`: A posts user 1's expense category id and receives the `direction=expense` message; posts user 1's second income category and `user_preferences` for user 1 changes `5 -> 23`; posts an empty value and user 1's row is deleted; A's own income category returns 422.
- **Impact:** the owner's fiscal-month window (`services/budget.py:421`) can be changed or reset by another user; metadata of user 1's categories (existence, direction) is readable by anyone signed in.
- **Mitigation:** add `user_id: int = Depends(current_user_id)` and pass it on; two-user integration test (user 2 writes own row, user 1 untouched, user 2 cannot probe user 1's ids); architecture test banning integer-literal `user_id` under `web/` and `services/`.
- **Effort:** S. **Related:** D-01, ADR-0025, ADR-0061 §5.

### H2-02 | Medium | Confirmed | missing-invariant-test | Formula save path skips the source-category validation that preview performs

- **Location(s):** `web/routers/recurring.py:181-230` (`_resolve_amount_inputs`, used by create at `:268` and update at `:632`); the check exists only in `services/recurring_formula.py:467-520` (`_invalid_source_ids`, called from `preview`).
- **Description:** `preview` rejects unknown, archived or foreign category ids with `invalid_source` and a non-positive result with `non_positive`. `POST /recurring` and `POST /recurring/{id}` call only `build_term`, `validate_formula_sources` (a cycle check, scoped to the caller's rules) and `compute_formula_amount`. V's category ids, a nonexistent id, or a mix are persisted in `amount_formula`, and a rule with a computed amount of 0 is stored (`default_amount = 0`).
- **Evidence:** `repro/H2/h2_03_formula_foreign_sources.py`: preview of V's category gives 422; create with `source_category_ids=[V.cat]` returns 200 and saves `{"source_category_ids":[8]}` with `default_amount 0`; same for a nonexistent id, a mixed list and the update path; promoting the stored rule creates a transaction.
- **Impact:** no cross-user leak today: evaluation filters on `user_id` (checked: V's 9 876.54 rule never shows in A's ledger, today, plan, forecast views), so a foreign id sums to 0. It is a latent isolation hole (any future global or shared category would make the stored foreign id live) and a correctness gap (zero-amount rules the UI says are invalid).
- **Mitigation:** in `_resolve_amount_inputs` call the same validator preview uses (move `_invalid_source_ids` to a shared function and run it, plus the positive-amount rule, before save); extend the existing two-user formula test to the create/update paths.
- **Effort:** S. **Related:** D §7 H2-Q1, ADR-0047, ADR-0056 §4.

### H2-03 | Medium | Confirmed | silent-fallback | Batch undo replays the latest audit row of any operation, so a stale Undo leaves the rule or planned row in the wrong state, and writes no audit row

- **Location(s):** `web/routers/recurring.py:469-543` (`SELECT prev_json ... ORDER BY id DESC LIMIT 1`, any operation; `set_next_due` is audit-free by its own docstring, `repositories/recurring.py:269-291`); `web/routers/planned.py:111-165` (latest `update` row). Related: B-03, B-11.
- **Description:** Undo is not tied to the batch: it restores `prev_json` of whatever audit row is newest for that entity. If the user edits the rule or planned row between the batch and the Undo click (toast still on screen, or a replayed request), the newest row is the edit, so the "restore" writes the post-promote state back. The promoted transactions are still soft-deleted and the toast still says "Undone". The undo itself is a mutation of `recurring_rules` / `planned_transactions` with **no audit row** (ADR-0019).
- **Evidence:** `repro/H2/h2_02_undo_chain.py`: recurring: promote (`next_due 2026-12-05`), edit description, Undo returns 204 and `next_due` stays `2026-12-05` while the promoted txn is deleted (the November occurrence is lost); audit rows added by undo: 0. Planned: after the edit the undo leaves `promoted_to_txn_id = 5` pointing at a soft-deleted transaction, so the row disappears from Upcoming. Same script proves the cross-user part is clean (A replaying V's payload changes nothing).
- **Impact:** own-data wrong state (a skipped occurrence, an orphaned promotion link) behind an "Undone" confirmation; no cross-user effect. The undo also soft-deletes any own txn ids posted (the id list is trusted client input), which is by design for a one-user-per-session model.
- **Mitigation:** snapshot the pre-batch state server-side keyed by a batch id (audit `batch_id` column or a small `promotion_batches` table scoped by `user_id`), undo only entries of that batch and only if the entity is unchanged since (compare `updated_at`); write audit rows from the same service function that does the reverse.
- **Alternatives:** keep audit replay but require the newest audit row to carry the batch's marker and refuse otherwise (cheaper, less robust).
- **Effort:** M. **Related:** B-03, B-11, D §7 H2-Q3.

### H2-04 | Low | Confirmed | security-control | One user can lock another out of password login from the same IP

- **Location(s):** `web/routers/auth.py:116-141` (`login_rate_limit`, key `"{ip}|email={email}"`), `services/rate_limit.py` (counts first, throttled attempts included).
- **Description:** the per-(IP, email) bucket is limited to 5 per minute and 20 per hour regardless of who sends the attempts. Anyone on the same client IP (two users behind one NAT, one tailnet node, or a spoofed `X-Forwarded-For`, see H3-Q2) can burn V's bucket with wrong passwords; V's correct password is then answered with 429 and, because throttled attempts count, one request a minute keeps V locked out.
- **Evidence:** `repro/H2/h2_07_login_lockout_and_audit_tail.py` (a): 5 wrong attempts then V with the correct password gets `429 Retry-After: 36`; A's own email bucket is unaffected.
- **Impact:** targeted login denial for a household user; the passkey path is a separate bucket.
- **Mitigation:** do not count throttled attempts toward the window, and reset the (IP, email) bucket on a successful login; optionally key the email bucket only on failures.
- **Effort:** S. **Related:** D-06, H3-Q2, ADR-0072.

### H2-05 | Low | Confirmed | htmx-contract | Admin edge cases: an absent `is_admin` field means demote; concurrent admin changes surface "database is locked" as a 500

- **Location(s):** `web/routers/settings_users.py:77-78,228-264` (`_checkbox(None)` is `False`, used as the new `is_admin`); `services/users.py:385-392` (`_atomically` opens a deferred `BEGIN`), `repositories/_shared.py:113-143`.
- **Description:** (1) `POST /settings/users/{id}` without an `is_admin` field demotes the target. The HTML form always sends the checkbox, but any other client or a trimmed form silently strips admin rights (target may be another admin, or self). Admin rights are lost with only a re-auth step. (2) The last-admin check reads the count and writes in a deferred transaction. In WAL mode the second writer gets `SQLITE_BUSY_SNAPSHOT`, so the invariant is kept, but the loser raises `OperationalError` (HTTP 500) instead of the 409 conflict.
- **Evidence:** `repro/H2/h2_04_admin_chain.py`: (2) ADM renames ADM2 without the field, ADM2's `is_admin` goes 1 to 0; self-demotion works while another admin exists and is effective on the next request; barrier-forced mutual deletion of the only two admins ends with exactly 1 live admin, and the other call raising `OperationalError: database is locked`. Last-admin demote/delete and self-delete return 409 as designed. Non-admin mass assignment is clean.
- **Impact:** admin lockout risk is low (invariant holds); mostly a robustness and surprise issue.
- **Mitigation:** treat a missing `is_admin` as "unchanged" (or require an explicit hidden `0`); open the admin mutations with `BEGIN IMMEDIATE` and map `OperationalError` to the 409 flow.
- **Effort:** S.

## 4. Questions

1. **Production user count.** Is more than one active user planned or present in prod? That decides whether H2-01 is Critical (as D-01).
2. **Cross-IP variant of H2-04.** Does Caddy overwrite `X-Forwarded-For` (H3-Q2)? If not, any authenticated or anonymous caller can lock out V from any IP by spoofing V's address.
3. **Remote FX effects.** A user chooses an account currency code, which drives fetches to the rate provider and writes to the shared `fx_rates` cache. Not testable here (no outbound traffic); is the provider response validated enough (rate range, currency pair) so one user's currency cannot poison conversion for others? Probe against a stubbed provider in a later pass.
4. **Concurrent HTTP undo.** The undo race was reasoned (writes are owner-scoped, last-write-wins on own rows) and tested sequentially, not with parallel HTTP requests. Worth a stress test only if H2-03 is fixed with batch ids.
