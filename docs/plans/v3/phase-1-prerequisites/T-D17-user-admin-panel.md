# T-D17 — User admin panel (`/settings/users`)

- **Phase**: 1 — App Prerequisites
- **Parallel-safe**: no — depends on auth + repository sweep
- **Depends on**: T-D02, T-D16
- **Blocks**: T-D43 (prod smoke journey exercises this flow end-to-end)
- **References**: [ADR-0061](../../../adr/0061-v3-multi-user-admin-bootstrap-and-data-isolation.md) §4, [ADR-0073](../../../adr/0073-user-admin-panel-guard-and-one-shot-password.md) (guard placement, toast delivery, 409/422 contract, audit attribution)

## Context

The admin bootstrapped by Terraform (T-D19) manages the user roster through an admin-only panel in Settings. Admin can add, edit, soft-delete users and reset passwords. Admin cannot see other users' data. The last-admin invariant is enforced in the service layer.

## Deliverables

1. **Middleware** `src/budget_planner/web/middleware/admin.py`:
   - `AdminRequiredMiddleware` — if `request.state.user.is_admin == 0`, return `404 Not Found` (not 403) to avoid admin-surface fingerprinting. Applied to the `/settings/users*` subtree only.
2. **Service layer** `src/budget_planner/services/users.py`:
   - `list_live_users(conn) -> list[User]` — admin view of all live users.
   - `create_user(conn, actor_user_id, email, name, is_admin) -> tuple[User, str]` — generates password via `secrets.token_urlsafe(16)`, bcrypt-hashes it, inserts the user, seeds per-user system categories (`Transit`, `Reconciliation`) in the same transaction. Returns `(user, plaintext_password)` — plaintext returned once for the toast; **never persisted or logged**.
   - `edit_user(conn, actor_user_id, user_id, *, email=None, name=None, is_admin=None)` — case-insensitive email uniqueness check; last-admin invariant check (cannot demote).
   - `reset_password(conn, actor_user_id, user_id) -> str` — regenerates password, sets `must_change_password = 1`, returns plaintext once.
   - `soft_delete_user(conn, actor_user_id, user_id)` — refuses if `user_id == actor_user_id`; refuses if target is the last live admin; sets `deleted_at`; revokes all target's sessions in the same transaction.
   - Every mutation writes an `audit_log` row with `entity_type='users'`, `entity_id=target_user_id`, `actor_user_id=admin_user_id`, `operation`, `prev_json`, `new_json`.
3. **Repository layer** extends `src/budget_planner/repositories/users.py` with `list_live`, `create`, `update`, `soft_delete`, `get_by_email_live`, `count_live_admins`. All functions take `conn` first; admin ops do not take `user_id` scoping (admin acts on the user table as a whole, which is the only user-owned-adjacent table that the admin manages).
4. **Router** `src/budget_planner/web/routers/settings_users.py`:
   - `GET /settings/users` — list view with per-row Edit / Reset password / Remove.
   - `POST /settings/users` — create user; response is a HTMX swap into `#new-password-toast` showing the generated password **once** with copy-to-clipboard.
   - `GET /settings/users/{id}/edit` — edit slide-over.
   - `POST /settings/users/{id}` — save edits.
   - `POST /settings/users/{id}/reset-password` — reset; toast shows new password once.
   - `POST /settings/users/{id}/delete` — soft-delete.
   - Mounted under `AuthRequiredMiddleware` + `AdminRequiredMiddleware`.
5. **Templates**:
   - `templates/settings/users/list.html` — table of live users (email, name, admin badge, created_at, last session), with "Add user" affordance.
   - `templates/settings/users/_row.html` — HTMX partial for a single row.
   - `templates/settings/users/edit.html` — slide-over.
   - `templates/settings/users/_password-toast.html` — one-shot password display with copy button.
   - Settings sidebar partial updated to show the "Users" tab only when `request.state.user.is_admin == 1`.
6. **i18n**: UI chrome in English per ADR-0058.

## Acceptance criteria

- `pytest tests/unit/services/test_users.py` covers: create (seeds system categories), edit (uniqueness, last-admin demote refusal, self-demote refusal when actor is sole admin), reset_password (regenerates + flags must_change), soft_delete (session revocation + last-admin refusal + self-delete refusal).
- `pytest tests/integration/web/test_settings_users.py` covers: non-admin GET `/settings/users` → 404; admin GET → 200; create user → toast carries plaintext once and the plaintext is **not** in any audit row; delete last admin → 409 with specific message (ADR-0073 §3; invalid / duplicate email → 422).
- `frontend-visual-audit` sweep against `/settings/users` at 1440 / 1024 / 375 — zero `horizontalScroll`, zero `consoleErrors`.
- Audit log carries one row per admin action; `actor_user_id` is populated.

## Validation hook

```sh
just test tests/unit/services/test_users.py tests/integration/web/test_settings_users.py
just test-prod-stack
# admin logs in → /settings/users → add user → copy password from toast → log out → new user logs in with that password.
```
