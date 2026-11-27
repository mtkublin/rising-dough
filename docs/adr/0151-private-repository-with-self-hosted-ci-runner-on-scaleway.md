# ADR-0151: Private Repository With a Self-Hosted CI Runner on Scaleway

- **Status**: Proposed (2026-11-27)
- **Date**: 2026-11-27
- **Amends**: [ADR-0099](0099-release-and-environment-policy.md) (environments need GitHub Pro once private), [ADR-0120](0120-pre-commit-is-the-local-gate.md) (where the PR CI gate runs)
- **Relates to**: [ADR-0032](0032-v3-remote-deployment-scaleway-stardust-warsaw.md) (Scaleway `pl-waw`, cost model), [ADR-0100](0100-least-privilege-ci-credentials.md), [ADR-0108](0108-faster-ci-parallel-tests-and-change-based-inner-loop.md), [ADR-0111](0111-terraform-declared-host-state.md), [ADR-0121](0121-drill-gate-skip-for-non-deploy-prs.md), [ADR-0132](0132-ci-environments-split-by-data-sensitivity.md)
- **Tasks**: T-CS20..T-CS24 (`docs/plans/ci-speed/tasks.md`)

## Context

- The repository `mtkublin/rising-dough` is public. The operator wants to make it private.
- Public repositories get unlimited GitHub-hosted Actions minutes. A private repository on a personal account gets 2,000 min/month (Free) or 3,000 (Pro). After that, minutes are billed. The default spending limit is $0, so with no limit set, Actions stops for the rest of the month.
- **Usage (estimate, 2026-11-27; not a full measurement).** The 7 days to 2026-11-27 had at least 1,000 workflow runs (the listing stopped at 1,000), with about 4,700 minutes of run-level wall time. A sample of 142 runs (2026-10-28) gave 3.5 billable min/run, and billed minutes were 1.56× the raw job time (each job is rounded up to a whole minute). Assumed: 4,500–6,000 runs/month at 5–7 billable min/run, so **~20k–40k billable min/month (central ~30k)**. In the sample, CI used 36% of the minutes, Security 22%, drill 17%, Terraform 10%, and Lock check, release, build and Dependabot the rest. A full per-job measurement was stopped by the API rate limit. T-CS20 records it.
- **Hosted cost if private.** ~27k overage minutes at about $0.006/min (Linux 2-core) is **~$160/month (range $100–220)**, plus Pro ($4). VAT is extra. Trimming CI (cancel superseded runs, path filters, scheduled Security) might halve the usage, but it would not reach 3,000 minutes.
- **Free-plan limits on private repositories.** Environment `required_reviewers` (`prod`, `prod-restore-read`) and the `protect-main` / release-tag rulesets are not enforced on a private repository under GitHub Free. Keeping the ADR-0099 approval gate and the immutable tags needs Pro.
- **Secret-free workflows.** These workflows use no environment and no secret, and run on PRs, pushes or schedules: `ci.yml` (also `workflow_call` from `release.yml`), `e2e.yml`, `security.yml`, `visual.yml`, `lock-check.yml`, `a11y-perf.yml`, `mutation.yml`. Together they use about 90% of the minutes. Deploy workflows (`build.yml` with cosign keyless OIDC, `terraform.yml`, `release.yml`, `rollback.yml`, `drill*.yml`, `replace-rehearsal.yml`, `restore-drill.yml`, `tailnet-cleanup.yml`, `image-retention.yml`, `key-expiry.yml`, `litestream-plaintext-cleanup.yml`) use environments and secrets, but only a few hundred minutes a month.
- Prod already runs on Scaleway `pl-waw` (ADR-0032). The drill uses `DEV1-S` there (ADR-0032 amendment 2026-11-16), so `DEV1` types are available in the zone.

## Decision

1. **Go private on GitHub Pro.** Keep GitHub as the host. The workflows, environments, rulesets, `ci_environments.toml`, `check_github_settings.py`, GHCR and the PR flow stay as they are. Moving to another forge (GitLab, Codeberg, a self-hosted Forgejo, Bitbucket) is rejected; see below.
2. **Hybrid runners.**
   - Secret-free workflows (list in Context) run on a **self-hosted runner**.
   - Every job that uses a GitHub environment, a secret or OIDC stays on `ubuntu-latest`. That keeps prod and drill credentials off a host that runs unmerged code (ADR-0100, ADR-0132). Those jobs fit inside Pro's 3,000 included minutes.
   - A guard (T-CS23) fails if a job on the self-hosted label references `environment:`, `secrets.*` (except `GITHUB_TOKEN`) or `id-token: write`.
3. **One switch, safe fallback.** Self-hosted jobs use `runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '"ubuntu-latest"') }}`.
   - Setting the repository variable `CI_RUNS_ON` to `["self-hosted","linux","x64","rd-ci"]` turns the runner on.
   - Deleting the variable falls back to hosted minutes. Use this when the runner is down or being rebuilt, and during the transition.
   - `release.yml`'s call to `ci.yml` uses the same expression, so a release can always fall back.
4. **Runner host.**
   - One **`DEV1-L`** (4 vCPU, 8 GB, 80 GB local SSD) in `pl-waw`, always on, with one Flex IPv4. github.com has no IPv6, so the host needs IPv4.
   - It runs two runner processes, so two jobs run at once. pytest uses `-n 2` on it (`PYTEST_WORKERS=2`).
   - It gets its own Scaleway project and a Terraform stack `terraform/ci-runner` with its own state key in the existing state bucket. It shares nothing with prod or drill: no tailnet, no prod bucket, no registry write.
5. **Host lifecycle.**
   - The host is disposable. Cloud-init installs Docker and the runner and registers it. It is rebuilt weekly and on demand by a hosted workflow, `ci-runner.yml`, in a new `ci-runner` environment that is `main`-only and holds the scoped Scaleway key and a fine-grained token.
   - The workflow mints a one-hour registration token and passes it in user data. No long-lived GitHub credential stays on the host.
   - Each job runs in a fresh container, and the workspace is cleaned between jobs. Caches (uv, npm, Playwright browsers, Docker layers) live on the local SSD, and a rebuild drops them.
6. **Accepted risk.**
   - A job with the Docker socket can take over the runner VM. The VM holds no secret beyond its runner registration.
   - A compromised dependency in a PR (for example a Dependabot PR) could tamper with later secret-free jobs on the same host, so it could fake a green `ci` check. It cannot reach prod.
   - `build.yml` builds and signs the release image on a hosted runner from `main`. The weekly rebuild limits how long tampering can persist.
7. **Spending guard.** Set a GitHub Actions spending limit (operator, T-CS24) that covers hosted fallback for a few days, about $25. Set a Scaleway billing alert at 2× the expected runner cost, as ADR-0032 does for prod.

## Consequences

- **Cost (estimate, list prices from memory, excluding VAT unless noted; check before acceptance):**

  | Item | €/month |
  |---|---|
  | `DEV1-L`, 730 h at ~€0.042/h | ~30.7 |
  | Flex IPv4 | 2.92 |
  | Image snapshot (optional) | ~1 |
  | Egress / ingress, Object Storage cache (75 GB free), Cockpit (free tier), security group | 0 |
  | **Scaleway subtotal** | **~34.6 (~42.6 with 23% VAT)** |
  | GitHub Pro ($4) | ~3.7 |
  | **Total** | **~€46/month (~200 PLN)** |

  The alternative is ~$165/month (range $105–225) on hosted minutes. A second `DEV1-L` (for parallel orchestrator waves) brings the runner to about €85/month with VAT.
- **Open price risk.** GitHub announced a per-minute charge for self-hosted runner minutes on private repositories (about $0.002/min), then postponed it. If it is in force, ~27k minutes add about $55/month, and the total becomes about €95/month. That is still below the hosted cost. Check before acceptance.
- **Speed.** One 4-vCPU host with two job slots is slower than many parallel hosted runners, so orchestrator waves queue in CI. The ADR-0108 job-time targets were measured on hosted runners, and T-CS22 re-measures them on the runner.
- **Operations.** About 1–2 h/month for OS patches (unattended-upgrades), runner version updates (the weekly rebuild takes the latest), and disk cleanup. The runner is a new failure domain for PR CI. The fallback switch is the mitigation.
- The `drill-gate` commit status, `e2e.yml` as a required check, the visual gate and ADR-0121's docs-only skip are unchanged. Only where the jobs run changes.
- The repository's public visibility no longer serves as the reason for any setting. Existing secret hygiene (`detect-secrets`, no secrets in the repo) stays.

## Alternatives rejected

- **Stay public.** No cost and no change, but the operator wants the code private.
- **Private, hosted minutes only.** Simplest, but ~$105–225/month, which is several times the self-hosted cost. With the default $0 limit, CI simply stops mid-month.
- **Trim CI to fit Pro's 3,000 minutes.** The estimate is 20k–40k; halving it is plausible, getting under 3,000 is not without dropping required checks. Trimming stays worthwhile on its own (T-CS21).
- **Move to GitLab, Codeberg, a self-hosted Forgejo/Gitea or Bitbucket.** Each would mean rewriting 22 workflows, the environment and approval model (ADR-0099, ADR-0100), the settings guards (`test_workflow_secrets.py`, `check_github_settings.py`), GHCR and the drill-gate commit status. Their free CI is smaller, so a self-hosted runner would be needed anyway. Protected environments with approvals are paid or missing.
- **A bigger dedicated host (`POP2-8C`, ~€240/month with VAT).** It costs more than the hosted minutes it replaces.
- **On-demand runners (one VM per job).** The cheapest compute, but there is no maintained autoscaler for Scaleway, so it would need a controller of our own. Revisit if the always-on host is idle most of the day.
- **Runner on the prod VM or a laptop.** The prod VM must not run unmerged code (ADR-0132) and is sized for the app (1 GB). A laptop runner works only while the laptop is on.
