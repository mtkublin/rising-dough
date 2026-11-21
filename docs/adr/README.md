# Architecture Decision Records

Numbered, append-only. See [ADR-0001](0001-record-architecture-decisions.md) for the process.

Status line convention: `Accepted (amended by ADR-N ...)`; a dated addendum at the end of an ADR corrects drift without deleting prior text. Numbers 0105 and 0121 are each used twice and 0044 is unused; these are grandfathered (not renumbered, to keep references stable) and `tests/architecture/test_adr_index.py` fails on any other duplicate or gap. The next new ADR takes the next free number.

| # | Title |
|---|-------|
| 0001 | [Record Architecture Decisions](0001-record-architecture-decisions.md) |
| 0002 | [Web Stack — FastAPI + HTMX + Jinja2 + Tailwind (CDN) + Plotly](0002-web-stack-fastapi-htmx-jinja.md) | (addendum 2026-11-21: Tailwind is local, charts are server SVG; see ADR-0027, ADR-0123)
| 0003 | [Database — SQLite Only in v1, DuckDB Attach Deferred](0003-database-sqlite-only-v1.md) |
| 0004 | [Package Manager — uv](0004-package-manager-uv.md) |
| 0005 | [Single User, No Auth, user_id Scaffolded](0005-single-user-no-auth-user-id-scaffold.md) (superseded by ADR-0061) |
| 0006 | [Multi-Currency Model](0006-multi-currency-model.md) |
| 0007 | [Timezone Handling](0007-timezone-handling.md) |
| 0008 | [Transaction Amount Sign & Direction](0008-transaction-amount-sign-and-direction.md) |
| 0009 | [Transit as a Single Row](0009-transit-single-row-model.md) |
| 0010 | [Account Model — Free-Text Type](0010-account-model-free-text-type.md) |
| 0011 | [Derived Balance, Manual Snapshots, Reconciliation](0011-derived-balance-snapshots-reconciliation.md) |
| 0012 | [Planned → Actual Promotion is Manual](0012-planned-manual-promotion.md) |
| 0013 | [Recurring Rules — Virtual Occurrences with Sparse Overrides](0013-recurring-virtual-occurrences-and-overrides.md) |
| 0014 | [Budget Model — Flat Categories, No Rollover, Three-Tier Resolution](0014-budget-flat-no-rollover-three-tier.md) |
| 0015 | [Forecasting — Deterministic Projection, Live via HTMX](0015-forecast-deterministic-live-htmx.md) |
| 0016 | [Task Runner — just](0016-task-runner-just.md) |
| 0017 | [Pre-commit Stack & Using Ruff Instead of Black](0017-precommit-ruff-instead-of-black.md) |
| 0018 | [CI — Single Matrix Row (Python 3.12 + Ubuntu)](0018-ci-single-matrix-row.md) |
| 0019 | [Soft Delete + Polymorphic Audit Log](0019-soft-delete-and-audit-log.md) |
| 0020 | [Import Deferred to a later version, Export in v1](0020-import-deferred-export-v1.md) |
| 0021 | [Functional Style, No Gratuitous OOP](0021-functional-style-no-oop.md) |
| 0022 | [Repository Layer: Soft-Delete + Audit Discipline](0022-repository-layer-soft-delete-audit-discipline.md) |
| 0023 | [UX Redesign — Information Architecture Consolidation + Interaction Model](0023-ux-redesign-information-architecture.md) | (addendum 2026-11-21: shipped nav and no FAB)
| 0024 | [Liability Accounts and Credit Limit](0024-liability-accounts-and-credit-limit.md) |
| 0025 | [User Preferences and Income Anchor](0025-user-preferences-and-income-anchor.md) |
| 0026 | [Quick-add FAB Visibility Scope](0026-fab-visibility-scope.md) | (addendum 2026-11-21: FAB removed)
| 0027 | [Frontend Toolchain Hardening — Local Tailwind, Stylelint, Partials, Visual Regression](0027-frontend-toolchain-hardening.md) |
| 0028 | [Ledger Segmented Control — Full Navigation, Not Partial Swap](0028-ledger-segmented-full-nav.md) |
| 0029 | [SQLite Connection Threading — `check_same_thread=False`, Per-Request Connection](0029-sqlite-connection-threading.md) |
| 0030 | [Shared Form Interaction Primitives](0030-shared-form-interaction-primitives.md) |
| 0031 | [Budget Page Composition v2: Income Anchor to Settings, Explicit "+ Rule" Create Affordance](0031-budget-page-composition-v2.md) |
| 0032 | [v3 Remote Deployment — Scaleway Stardust Warsaw + Scaleway Object Storage](0032-v3-remote-deployment-scaleway-stardust-warsaw.md) (renumbered v2 → v3 on 2026-10-28) |
| 0033 | [v3 Authentication — Single-User Passkey (WebAuthn) + Fallback Password](0033-v3-auth-single-user-passkey.md) (renumbered v2 → v3 on 2026-10-28) |
| 0034 | [v3 SQLite Durability — Continuous Replication via Litestream to Scaleway Object Storage](0034-v3-sqlite-replication-litestream.md) (renumbered v2 → v3 on 2026-10-28) |
| 0035 | [v3 Infrastructure as Code — Terraform (Scaleway Provider) + Cloud-Init Bootstrap](0035-v3-infrastructure-as-code-terraform.md) (renumbered v2 → v3 on 2026-10-28) |
| 0036 | [v3 Reverse Proxy & TLS — Caddy with Automatic HTTPS](0036-v3-reverse-proxy-caddy-auto-tls.md) (renumbered v2 → v3 on 2026-10-28) | (Accepted; addendum 2026-11-21: stock caddy:2.8, rate limiting in the app per ADR-0072)
| 0037 | [v3 Deployment Pipeline — GitHub Actions SSH Deploy with Immutable Image Tags](0037-v3-github-actions-deploy-pipeline.md) (renumbered v2 → v3 on 2026-10-28) |
| 0038 | [Recurring Rules — Standalone Lifecycle with `next_due` + Direct Promotion](0038-recurring-standalone-lifecycle.md) (supersedes ADR-0013; amends ADR-0012) |
| 0039 | [Budget "Left to Spend per Day" Includes Recurring Commitments](0039-budget-daily-spend-includes-recurring.md) (amends ADR-0025 §F4.6, ADR-0038) |
| 0040 | [Modal Dismissal Fires on Form Submit Only, Not Side-Effect HTMX Requests](0040-modal-dismissal-scope.md) (amends ADR-0030 §5) |
| 0041 | [Budget "Period" is Last-Anchor-Income to Next-Anchor-Income, Not Calendar Month](0041-budget-period-anchor-window.md) (amends ADR-0025 §F4.6, ADR-0039) |
| 0042 | [Forecast — Budget Overlay for Unaccounted Expected Spend](0042-forecast-budget-overlay.md) (supersedes ADR-0015 §Alternatives in part) |
| 0043 | [Forecast Surface — Monthly Horizon + Breakdown Table](0043-forecast-tab-monthly-horizon-and-table.md) (amends ADR-0015) |
| 0045 | [Recurring Rules — Formula-Derived Amount (Percentage of Other Rules)](0045-recurring-formula-amount.md) (amends ADR-0013, ADR-0038) |
| 0046 | [Recurring Overrides — Soft-Consume on Promotion (Not Delete)](0046-recurring-override-soft-consume.md) (amends ADR-0038 §Promotion-flow step 6e) |
| 0047 | [Recurring Formula — Linear Combination of Terms + Chained Formulas](0047-recurring-formula-linear-combination-and-chaining.md) (supersedes ADR-0045 §Decision) |
| 0048 | [Category Color Coding — Per-Category Override with Direction Default](0048-category-color-coding.md) (amends ADR-0023; extends F1.6) |
| 0049 | [Budget Monthly Summary — Surface Analytics Columns (Avg/mo, YTD avg, Δ prev)](0049-budget-monthly-summary-analytics-columns.md) (amends ADR-0031 §Monthly summary; surfaces F4.5) |
| 0050 | [v2 Rising Dough — Product Rename and Visual Direction](0050-v2-rising-dough-rename-and-visual-direction.md) (supersedes ADR-0023 §Design direction; amends ADR-0048) |
| 0051 | [v2 Rising Dough — Information Architecture (Today · Ledger · Plan · Accounts · Settings)](0051-v2-information-architecture-rising-dough.md) (supersedes ADR-0023 §Information architecture) |
| 0052 | [v2 Rising Dough — Tailwind v4 Migration, `@theme` Tokens, and Self-Hosted Fonts](0052-v2-tailwind-v4-tokens-and-font-hosting.md) (amends ADR-0027) | (Accepted in part; addendum 2026-11-21: Tailwind v4 not adopted)
| 0053 | [v2 Rising Dough — Component System and Jinja Macro Inventory](0053-v2-component-system-and-jinja-macros.md) |
| 0054 | [v2 Rising Dough — Charts Move From Plotly to Server-Rendered SVG](0054-v2-charts-plotly-to-server-svg.md) (supersedes ADR-0002 §Plotly) |
| 0055 | [v2 Rising Dough — Responsive Layer and Mobile Shell](0055-v2-responsive-layer-mobile-first.md) (supersedes ADR-0023 §"no mobile adaptive nav") |
| 0056 | [v2 Rising Dough — Inline Interactions, Live Previews, and Backend Additions](0056-v2-inline-interactions-and-backend-additions.md) (amends ADR-0026) |
| 0057 | [v2 — Archived categories on recurring rules (allow, mute, block creation)](0057-v2-archived-categories-on-recurring-rules.md) (amends ADR-0048) | (addendum 2026-11-21: archived-category validation not implemented)
| 0058 | [v2 — UI language: English chrome, user data as-typed](0058-v2-ui-language-english-chrome.md) (amends ADR-0051) |
| 0059 | [v2 — Pace-tag rule for Today hero and pace_tag macro](0059-v2-pace-tag-rule.md) (amends ADR-0041) |
| 0060 | [v2 — Unified Entry Modal (Happened / Planned / Repeats)](0060-v2-unified-entry-modal.md) (supersedes ADR-0030 §4 per-mode chrome; amends ADR-0047 formula UI) |
| 0061 | [v3 Multi-User — Admin Bootstrap, User Admin Panel, Per-User Data Isolation](0061-v3-multi-user-admin-bootstrap-and-data-isolation.md) (supersedes ADR-0005; amends ADR-0033, ADR-0022, ADR-0019) |
| 0062 | [Recurring Override Overlay — Align With Plan/Budget `rd-override` Card](0062-recurring-override-overlay-alignment.md) (amends ADR-0031, ADR-0030) |
| 0063 | [Recurring Rules — User-Facing Stop Date](0063-recurring-stop-date.md) (amends ADR-0038) |
| 0064 | [Plan / Today / Overview Default Landing Month Follows the Fiscal Cycle](0064-plan-default-fiscal-month.md) (amends ADR-0041; surfaces F4.6) |
| 0065 | [CSRF Cookie Name Is Env-Dependent; HTMX Reads the Token From a `<meta>` Tag](0065-csrf-dev-cookie-name-and-meta-token.md) (amends ADR-0033 §4) |
| 0066 | [Orchestrator Mode Skill for Parallel Multi-Agent Work](0066-orchestrator-mode-skill.md) |
| 0067 | [Auth Backend — Opaque Server-Side Sessions, Caller-Held Passkey Challenges](0067-auth-backend-sessions-and-passkey-challenges.md) (amends ADR-0033 §1, §3, §6) |
| 0068 | [User-Scoping Static Check — Scope, Rules, and Allowlist Policy](0068-user-scoping-static-check-policy.md) (extends ADR-0022, ADR-0061 §5) |
| 0069 | [Admin Bootstrap — Per-Environment Policy, Legacy-Row Adoption, Operator Password CLI](0069-admin-bootstrap-env-policy-and-operator-cli.md) (amends ADR-0061 §3) |
| 0070 | [Auth Web Layer — Cookie Names, Unauthenticated Responses, Middleware Order](0070-auth-web-layer-cookies-middleware-order.md) (amends ADR-0033 §3, §5) |
| 0071 | [Production Startup Migrations — Container Entrypoint, Restore-Before-Start, N-1 Rollback Policy](0071-production-startup-migrations.md) (extends ADR-0069, ADR-0034, ADR-0037 §3) |
| 0072 | [Auth Rate Limiting — In-House Fixed-Window Counters on `auth_rate_limit`](0072-auth-rate-limit-sqlite-fixed-window.md) (amends ADR-0033 §2) |
| 0073 | [User Admin Panel — 404 Guard, One-Shot Password Delivery, Invariant Errors, Audit Attribution](0073-user-admin-panel-guard-and-one-shot-password.md) (amends ADR-0061 §4, §5) |
| 0074 | [Password Change — Policy, Audit Shape, and Forced-Rotation Responses](0074-password-change-policy-and-forced-rotation.md) (amends ADR-0061 §4) |
| 0075 | [Security Controls Live in Settings — Security Tab, Redirects, Forced-Rotation Page](0075-security-controls-live-in-settings.md) (amends ADR-0070, ADR-0073, ADR-0074) |
| 0076 | [Session Hardening — Absolute Lifetime Cap, Step-Up Re-Auth, Hashed Session Ids](0076-session-hardening-absolute-cap-step-up-hashed-ids.md) (amends ADR-0067 §2, ADR-0070 §2–§3) |
| 0077 | [Retire Legacy Home Page; Today Is the Landing Page](0077-retire-legacy-home-page.md) (amends ADR-0051, ADR-0023, ADR-0070 §4) |
| 0078 | [v3 Data-Protection Quick Wins — Close Cross-User Leaks, Bound Copies, Encrypt Backups](0078-v3-data-protection-quick-wins.md) (amends ADR-0034 §3, ADR-0071) |
| 0079 | [v4 Threat Model and Data-Protection Approach](0079-v4-threat-model-and-data-protection-goals.md) (amends ADR-0061; lifts v3 non-goals "admin visibility" / "hard delete") |
| 0080 | [v4 Envelope Encryption — Key Hierarchy, Server Secrets, Session Binding](0080-v4-envelope-encryption-key-hierarchy-and-sessions.md) (amends ADR-0067, ADR-0070 §2, ADR-0076, ADR-0019) |
| 0081 | [v4 Field-Level Encryption — Column Scope, Query Model, Feature Preservation](0081-v4-field-level-encryption-scope-and-query-model.md) (amends ADR-0022, ADR-0068, ADR-0019, ADR-0071) |
| 0082 | [v4 Account Lifecycle Under Encryption — Onboarding, Credentials, Recovery, Migration](0082-v4-account-lifecycle-recovery-and-migration.md) (amends ADR-0061, ADR-0069, ADR-0073, ADR-0074, ADR-0075) |
| 0083 | [v4 Right to Be Forgotten, Data Portability, Retention Schedule, Keyless Operations](0083-v4-right-to-be-forgotten-portability-and-retention.md) (amends ADR-0019, ADR-0034, ADR-0061, ADR-0073, ADR-0078) |
| 0084 | [v3 Compute Zone `pl-waw-2` and Ubuntu 24.04 (`ubuntu_noble`) Image Slug](0084-v3-compute-zone-pl-waw-2-and-ubuntu-noble-image.md) (amends ADR-0032) |
| 0085 | [Budget "Left" Counts Only Commitments in Budgeted Categories](0085-budget-left-counts-only-budgeted-commitments.md) (amends ADR-0039, ADR-0041; amended by ADR-0092) |
| 0086 | [Formula Sources Honour Per-Occurrence Overrides in Chains](0086-formula-source-overrides-honoured-in-chains.md) (clarifies ADR-0046, ADR-0047) |
| 0087 | [Forecast Honours Recurring `next_due`](0087-forecast-honours-recurring-next-due.md) (amends ADR-0043) |
| 0088 | [DNS Zone Is Not Owned by Any Env Terraform State](0088-dns-zone-not-owned-by-env-state.md) (amends ADR-0035) |
| 0089 | [Accounts Tab Planned Net per Account](0089-accounts-planned-net-per-account.md) (relates to ADR-0085, ADR-0087) |
| 0090 | [Terraform >= 1.10 Minimum and CI Pin to 1.17.1](0090-terraform-minimum-1-10-ci-pin.md) (amends ADR-0035) |
| 0091 | [Bucket Policy Is an Explicit Allow-List; Per-Env Isolation](0091-bucket-policy-allow-list-per-env-isolation.md) (amends ADR-0035, ADR-0032) |
| 0092 | [Drill in Its Own Scaleway Project; Stable Restore-Reader Principal](0092-drill-in-separate-scaleway-project.md) (supersedes ADR-0091 shared-project assumption; relates to ADR-0088, ADR-0035) |
| 0093 | [CI Terraform Inputs via TF_VAR_* from Environment Secrets](0093-ci-terraform-inputs-via-tf-var-environment-secrets.md) (amends ADR-0092 §4, ADR-0078 §3; amended 2026-11-19, T-D159: non-secret flags such as `MANAGED_DNS_ZONE` are variables) |
| 0094 | [SSH Only Over Tailscale; Port 22 Closed to the Internet](0094-ssh-only-over-tailscale-port-22-closed.md) (amends ADR-0035, ADR-0032; relates to ADR-0037, ADR-0069, ADR-0088) |
| 0095 | [Budget `committed` Converts to Base Currency](0095-budget-committed-converts-to-base-currency.md) (amends ADR-0085) |
| 0096 | [Terraform State Bucket Bootstrapped by a Separate Terraform Root Stack](0096-terraform-state-bootstrap-stack.md) (amends ADR-0035 §4; relates to ADR-0091, ADR-0093) |
| 0097 | [Per-Batch CI in Orchestrator Mode; Fast Pre-commit Pytest](0097-per-batch-ci-policy-and-fast-precommit-pytest.md) (amends ADR-0066; relates to ADR-0027) |
| 0098 | [Keep Rendered User-Data Secrets Out of Plan Output](0098-keep-rendered-user-data-secrets-out-of-plan-output.md) (relates to ADR-0032, ADR-0094) |
| 0099 | [Release and Environment Policy](0099-release-and-environment-policy.md) (amended 2026-11-21: tamper-resistant merge gate, T-Q239; required merge checks amended by ADR-0121; relates to ADR-0035, ADR-0037, ADR-0094, ADR-0096, ADR-0097, ADR-0098) |
| 0100 | [Least-Privilege CI Credentials per Environment, Separate Drill State Bucket, Key-Expiry Monitor](0100-least-privilege-ci-credentials.md) (amends ADR-0096; relates to ADR-0091, ADR-0093, ADR-0099) |
| 0101 | [Drill Environment Is Tailnet-Only; Drill Apply Is Human-Gated](0101-drill-environment-is-tailnet-only.md) (amends ADR-0092, ADR-0099, ADR-0100; relates to ADR-0036, ADR-0094) |
| 0102 | [Debian 13 (trixie) Base Image](0102-debian-13-trixie-base-image.md) (amends ADR-0032; relates to ADR-0099) |
| 0103 | [Image Scan Ignores Unfixed OS CVEs; Runtime Stage Applies Debian Upgrades](0103-image-scan-ignores-unfixed-os-cves.md) (amends ADR-0102; relates to ADR-0032, ADR-0099) |
| 0104 | [Env-Stack IAM Moves to the Local Bootstrap; CI Loses IAMManager](0104-iam-in-local-bootstrap-no-iammanager-for-ci.md) (amends ADR-0100; relates to ADR-0091, ADR-0092, ADR-0098, ADR-0099) |
| 0105 | [Committed Includes Every Overdue Unpromoted Item](0105-committed-includes-all-overdue-items.md) (amends ADR-0039; relates to ADR-0043, ADR-0085, ADR-0087, ADR-0089) |
| 0105 | [CI Identities in the Durability Bucket Policies](0105-ci-principals-in-durability-bucket-policies.md) (amends ADR-0091, ADR-0100; relates to ADR-0099, ADR-0104) |
| 0106 | [UI Behaviour Test Harness Ahead of the Sourdough Redesign](0106-ui-behaviour-test-harness.md) (amends ADR-0027 §4; relates to ADR-0107, ADR-0066, ADR-0097) | (Accepted, implementation pending; OQ-23)
| 0107 | [Sourdough Redesign Built Solely From the Designer Handoff](0107-sourdough-redesign-from-designer-handoff.md) (supersedes ADR-0052, ADR-0053, ADR-0055, ADR-0050 visual direction; amends ADR-0027 §1–§3, ADR-0054, ADR-0056; relates to ADR-0106, ADR-0099) | (Accepted, implementation pending; OQ-23)
| 0108 | [Faster CI — Parallel Tests, Change-Based Inner Loop, Full Suite at the Gates](0108-faster-ci-parallel-tests-and-change-based-inner-loop.md) (amends ADR-0097, ADR-0018; relates to ADR-0066, ADR-0099, ADR-0106) |
| 0109 | [Prod Releases Triggered by GitHub Releases on `main`](0109-release-from-github-release-tags.md) (amends ADR-0099) |
| 0110 | [One Prod Approval per Release](0110-single-prod-approval-per-release.md) (amends ADR-0099; relates to ADR-0100, ADR-0109) |
| 0111 | [Terraform-Declared Host State, Pulled by a Host Agent](0111-terraform-declared-host-state.md) (supersedes ADR-0037 deploy step and ADR-0110; amends ADR-0099) |
| 0112 | [Prod-Gated Cleanup of Plaintext Litestream Objects](0112-prod-gated-litestream-plaintext-cleanup.md) (amends ADR-0078 §3; relates to ADR-0099, ADR-0100) |
| 0113 | [CSP-Compatible Frontend — No Inline Script, Vendored Assets](0113-csp-compatible-frontend.md) (amends ADR-0036 `style-src`; relates to ADR-0027, ADR-0111) |
| 0114 | [Litestream Replicate Config Carries the Age Identity; One Forced New Generation](0114-litestream-replicate-identity-and-forced-generation.md) (amends ADR-0078 §3; relates to ADR-0111, ADR-0112) |
| 0115 | [A Drill VM Is Exclusive; Every Drill Workflow Starts With a Drill Lock](0115-drill-vm-is-exclusive-drill-lock.md) (amends ADR-0099; relates to ADR-0101, ADR-0092) |
| 0116 | [The Drill's Tailnet Name Is Unique Per Run](0116-drill-tailnet-name-unique-per-run.md) (amends ADR-0101; relates to ADR-0094, ADR-0099) |
| 0117 | [One Source for Shared GitHub Workflow Logic](0117-dry-github-workflows.md) (relates to ADR-0099, ADR-0111, ADR-0115, ADR-0116) |
| 0118 | [The VM Root Volume Is Local SSD, Declared Explicitly](0118-local-ssd-root-volume.md) (amends ADR-0032; relates to ADR-0035, ADR-0084, ADR-0099, ADR-0111, ADR-0114) |
| 0119 | [A Replication Freshness Health Path for the External Monitor](0119-replication-freshness-health-path.md) (relates to ADR-0033, ADR-0034, ADR-0078, ADR-0111, ADR-0114) |
| 0120 | [Pre-commit Is the Local Gate; the Full Suite Runs Only in PR CI](0120-pre-commit-is-the-local-gate.md) (amends ADR-0108 §4, ADR-0097; relates to ADR-0066, ADR-0099, ADR-0027) |
| 0121 | [Drill-Gate Skip for Non-Deploy PRs](0121-drill-gate-skip-for-non-deploy-prs.md) (amends ADR-0099; relates to ADR-0115) |
| 0121 | [Path-Filtered Workflows Are Not Required Checks](0121-path-filtered-workflows-are-not-required-checks.md) (amends ADR-0099; relates to ADR-0115, ADR-0120) |
| 0122 | [Domain Audit Rows Record Owner and Actor](0122-domain-audit-rows-record-owner-and-actor.md) (amends ADR-0019, ADR-0022, ADR-0061, ADR-0073; relates to ADR-0078) |
| 0123 | [Frontend Stays Server-Rendered (Jinja + HTMX); No SPA Framework; Animation via CSS and Web APIs](0123-frontend-stays-server-rendered-no-spa-framework.md) (renumbered from 0112; relates to ADR-0107, ADR-0027, ADR-0080, ADR-0081) |
| 0124 | [Savings Goals — Envelope Allocations and Net-Worth Goals](0124-savings-goals-envelopes-and-net-worth.md) (relates to ADR-0006, ADR-0019, ADR-0042, ADR-0056, ADR-0061, ADR-0081, ADR-0125) |
| 0125 | [The Sourdough Starter — Feed Signals, Health Score, Milestones, Shelf](0125-sourdough-starter-rules.md) (amended by ADR-0128; amends ADR-0011; relates to ADR-0124, ADR-0123, ADR-0041, ADR-0081) |
| 0126 | [Goals and Starter UI Built From a Designer Handoff Extending the Redesign](0126-gamification-design-handoff.md) (amended by ADR-0129; relates to ADR-0107, ADR-0123, ADR-0113, ADR-0106) |
| 0127 | [A Prod VM Replacement Is Safe Unattended](0127-safe-prod-vm-replacement.md) (amended 2026-11-19: drain before the replacing apply, T-D157; the drain-capable agent ships before the first replacing release, T-D158; amends ADR-0071, ADR-0094, ADR-0111, ADR-0118; relates to ADR-0034, ADR-0099, ADR-0110, ADR-0114) |
| 0128 | [Starter Tuning From Simulation](0128-starter-tuning-from-simulation.md) (amends ADR-0125; relates to ADR-0124, ADR-0014, ADR-0041) |
| 0129 | [The Goals and Starter Handoff Is Vendored as Its Own Folder, Delivered in One Drop](0129-goals-starter-handoff-vendored-standalone.md) (amends ADR-0126; relates to ADR-0107, ADR-0113, ADR-0123, ADR-0124, ADR-0125, ADR-0106) |
| 0130 | [Prevention Regime and Full Architectural Compliance](0130-prevention-regime-and-full-architectural-compliance.md) (amends ADR-0007, ADR-0021, ADR-0022, ADR-0066, ADR-0120; relates to ADR-0120, ADR-0097, ADR-0108, ADR-0099, ADR-0107, ADR-0131) |
| 0131 | [Mutation Testing Policy](0131-mutation-testing-policy.md) (relates to ADR-0130, ADR-0120, ADR-0108) |
| 0132 | [CI Environments Are Split by Data Sensitivity; Prod Replica Read Material Lives in One Gated Environment](0132-ci-environments-split-by-data-sensitivity.md) (amends ADR-0099, ADR-0100; relates to ADR-0101, ADR-0093, ADR-0104, ADR-0111, ADR-0121, ADR-0130) |
| 0133 | [Proxy-Set Client Identity and Bounded Auth Audit Text](0133-proxy-set-client-identity-and-bounded-auth-audit-text.md) (amends ADR-0072; relates to ADR-0032, ADR-0036) |
| 0135 | [Per-Drill Litestream Age Key Pair Generated in Terraform](0135-per-drill-age-keypair-in-terraform.md) (amends ADR-0132, ADR-0078; relates to ADR-0093, ADR-0101, ADR-0111) |
| 0136 | [Soft-Deleted Accounts Are Excluded From Balances, Stats and Converters](0136-soft-deleted-accounts-excluded-from-balances-stats-converters.md) (relates to ADR-0130, ADR-0008) |
| 0137 | [Write Transactions Begin IMMEDIATE and Guard Reads Live Inside Them](0137-begin-immediate-and-guard-reads-inside-the-transaction.md) (amends ADR-0019, ADR-0022; relates to ADR-0061, ADR-0073) |
