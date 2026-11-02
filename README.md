# Budget Planner

Local-first personal budget planning and fortune tracking. Single user, multi-account, multi-currency. Served on `127.0.0.1`.

## What this is

- Local-only web app. Binds to `127.0.0.1:8000`. No LAN exposure, no auth.
- SQLite file on disk; data stays on the machine.
- Python 3.12 / FastAPI / HTMX / Jinja2 / Tailwind (compiled locally; see [ADR-0027](docs/adr/0027-frontend-toolchain-hardening.md)) / Plotly.

## Prerequisites

| Tool | Why | Install |
|------|-----|---------|
| Python 3.12 | Runtime | `uv python install 3.12` |
| Node 20 + npm | Dev-only frontend toolchain — Tailwind build, stylelint, visual-regression diff helper (see [ADR-0027](docs/adr/0027-frontend-toolchain-hardening.md)) | `brew install node` / `nvm install 20` |
| [`uv`](https://docs.astral.sh/uv/) `>= 0.4` | Dependency + venv manager (see [ADR-0004](docs/adr/0004-package-manager-uv.md)) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [`just`](https://github.com/casey/just) | Task runner (see [ADR-0016](docs/adr/0016-task-runner-just.md)) | `brew install just` / `cargo install just` |

macOS and Linux are tested. Windows is unverified; use WSL.

Chromium is only needed for the Playwright e2e suite. The first run of `just install` does **not** fetch it automatically; without it the e2e suite auto-skips but the rest of CI stays green. Install once:

```sh
uv run playwright install chromium
```

## Quick start

```sh
git clone <repo-url> budget_planner
cd budget_planner
just install    # uv sync + install pre-commit hooks + npm ci
just css        # compile Tailwind once (one-off; `just dev` + `just css-watch` on separate panes thereafter)
just migrate    # apply pending SQL migrations into the dev SQLite file
just seed       # seed default categories (Transit, Reconciliation) and demo accounts
just dev        # start FastAPI with hot reload on http://127.0.0.1:8000
```

The first `uv sync` pulls `pyarrow` (~70 MB). One-off cost.

## Daily commands

| Command | Does |
|---------|------|
| `just dev` | FastAPI dev server, hot reload, `127.0.0.1:8000`. |
| `just css` | Build Tailwind once (purged + minified → `static/tailwind.css`). |
| `just css-watch` | Rebuild Tailwind on save; pair with `just dev`. |
| `just test` | Pytest with coverage; fails under 90%. |
| `just test-visual` | Playwright visual-regression snapshots (opt-in; not part of `just ci`). |
| `just test-visual-update` | Refresh visual baselines after an intentional design change. |
| `just lint` | `ruff` + `sqlfluff` + `djlint` + `stylelint`. |
| `just format` | `ruff format` + `ruff --fix` + `sqlfluff fix` + `djlint --reformat`. |
| `just typecheck` | `mypy --strict`. |
| `just ci` | Everything CI runs (lint, typecheck, test). |
| `just db-reset` | Recreate the dev DB from migrations + seed. **Destructive.** |
| `just migrate` | Apply pending migrations. |
| `just seed` | Insert seed data. |

## Where things live

Phase 6 ([ADR-0023](docs/adr/0023-ux-redesign-information-architecture.md)) collapsed the nine Phase 3 pages into **four primary tabs + a Settings drawer**. Legacy URLs 302-redirect to their new homes for one release before the Phase 7 cleanup.

| Tab | Route | Collapses | Deep dive |
|---------|-------|-----------|-----------|
| Overview | `/` | Home + Forecast summary + Analytics headline | [`docs/requirements.md`](docs/requirements.md) §3.9 |
| Ledger | `/ledger?view=actual\|planned\|recurring` | Transactions + Planned + Recurring | [ADR-0012](docs/adr/0012-planned-manual-promotion.md), [ADR-0013](docs/adr/0013-recurring-virtual-occurrences-and-overrides.md) |
| Accounts | `/accounts` | Balances + Snapshots + Reconcile | [ADR-0010](docs/adr/0010-account-model-free-text-type.md), [ADR-0011](docs/adr/0011-derived-balance-snapshots-reconciliation.md) |
| Budget | `/budget` | Budget rules + Monthly summary + Breakdown charts | [ADR-0014](docs/adr/0014-budget-flat-no-rollover-three-tier.md) |
| Settings (drawer) | `/settings?tab=categories\|fx\|prefs` | Categories + FX cache + Preferences | [ADR-0023](docs/adr/0023-ux-redesign-information-architecture.md) |
| Forecast (deep page) | `/forecast` | — | [ADR-0015](docs/adr/0015-forecast-deterministic-live-htmx.md) |

**Interaction model** ([ADR-0023](docs/adr/0023-ux-redesign-information-architecture.md)):

- **Quick-add FAB** — fixed bottom-right button; the target form adapts to the active page (`/transactions/new` on Overview, `/planned/new` on `/ledger?view=planned`, etc.).
- **Command palette** — `⌘K` / `Ctrl+K`.
- **Keyboard shortcuts** — `g o` Overview · `g l` Ledger · `g a` Accounts · `g b` Budget · `g s` Settings · `n` Quick-add · `/` focus search · `[` / `]` cycle Ledger views · `?` cheatsheet · `Esc` close topmost overlay.

## Project docs

- [`docs/requirements.md`](docs/requirements.md) — canonical requirements. Scope guard in §3.8.
- [`docs/tasks.md`](docs/tasks.md) — task breakdown by phase.
- [`docs/implementation_plan.md`](docs/implementation_plan.md) — phased plan + Definition of Done.
- [`docs/adr/`](docs/adr/README.md) — architecture decisions. Start at the index.
- [`docs/plans/`](docs/plans/) — per-task implementation plans. Agents read these first.
- [`CLAUDE.md`](CLAUDE.md) — agent handoff rules; docs-first policy.

## Configuration

Copy [`.env.example`](.env.example) to `.env` and edit. All keys are prefixed `BUDGET_`.

| Key | Default | Notes |
|-----|---------|-------|
| `BUDGET_DATABASE_URL` | `sqlite:///data/budget.sqlite` | SQLite only in v1 ([ADR-0003](docs/adr/0003-database-sqlite-only-v1.md)). |
| `BUDGET_BASE_CURRENCY` | `PLN` | Aggregates convert to this ([ADR-0006](docs/adr/0006-multi-currency-model.md)). |
| `BUDGET_DISPLAY_TIMEZONE` | `Europe/Warsaw` | Display tz ([ADR-0007](docs/adr/0007-timezone-handling.md)). |
| `BUDGET_BIND_HOST` | `127.0.0.1` | Loopback only; Caddy fronts TLS ([ADR-0005](docs/adr/0005-single-user-no-auth-user-id-scaffold.md) / [ADR-0036](docs/adr/0036-v3-reverse-proxy-caddy-auto-tls.md)). |
| `BUDGET_BIND_PORT` | `8000` | |
| `BUDGET_ENV` | `dev` | `dev` / `test` / `production`. Production flips DB default and requires `BUDGET_COOKIE_SECRET`. |
| `BUDGET_TRUSTED_HOSTS` | *(empty)* | Comma-separated. Fed to Starlette's `TrustedHostMiddleware` (T-D07). |
| `BUDGET_COOKIE_SECRET` | *(dev fallback)* | Required in production ([ADR-0033](docs/adr/0033-v3-auth-single-user-passkey.md)). |
| `BUDGET_SESSION_LIFETIME_DAYS` | `14` | Bounded 1..90. |
| `BUDGET_FX_API_URL` | `https://api.frankfurter.app` | FX source. |

Timestamps are UTC in the DB, dates on transactions are naive `DATE`, display defaults to `Europe/Warsaw`. See [ADR-0007](docs/adr/0007-timezone-handling.md).

## Data model one-liner

Amounts are stored as positive integer minor units; direction derives from `category.direction` ([ADR-0008](docs/adr/0008-transaction-amount-sign-and-direction.md)). Every mutable table is soft-delete with an audit trail — repositories enforce this, never bypass them ([ADR-0019](docs/adr/0019-soft-delete-and-audit-log.md), [ADR-0022](docs/adr/0022-repository-layer-soft-delete-audit-discipline.md)). See [`docs/requirements.md`](docs/requirements.md) §2 for the full schema.

## Accessibility

The four primary tabs plus the Settings drawer target WCAG 2.1 AA: semantic landmarks, keyboard navigation, visible focus rings, labelled inputs, announced HTMX swaps, 4.5:1 contrast. Native `<dialog>` (command palette, shortcuts cheatsheet) ships focus trap + Esc close for free; `role="dialog"` overlays (settings drawer, slide-over form) share a stack so `Esc` always closes the topmost one. Reduced-motion preference is honoured. Styles live in [`src/budget_planner/web/static/app.css`](src/budget_planner/web/static/app.css).

## Design

Editorial / Swiss direction: serif display, sans body, mono for numbers, hairline rules, generous page gutters, flat surfaces, single ink accent. Design tokens are CSS custom properties in [`src/budget_planner/web/static/app.css`](src/budget_planner/web/static/app.css); templates compose them rather than ship hard-coded colours. Default Tailwind utilities are allowed on top but used sparingly.

## Troubleshooting

- **`uv sync` fails on `pyarrow` wheels** → upgrade `uv` (`uv self update`), retry. `uv --version` as sanity check.
- **`just migrate` fails with `database is locked`** → close any open SQLite browser, retry.
- **Forecast page warns about FX fetch** → expected offline. Last-known rate is used ([ADR-0006](docs/adr/0006-multi-currency-model.md) fallback).
- **Pre-commit hook `detect-secrets` flags a file** → audit, run `uv run detect-secrets scan --baseline .secrets.baseline`, review the additions.
- **Playwright e2e tests skipped** → run `uv run playwright install chromium` once. The rest of CI stays green without it.

## Deployment

Not in v1. See [`docs/tasks.md`](docs/tasks.md) Phase 6 for the deferred list (Docker, hosting, auth).

## License

Personal project. All rights reserved.

## Status

v1 scope frozen at Phase 5. See [`docs/requirements.md`](docs/requirements.md) §3.8 for what is explicitly out of scope.
