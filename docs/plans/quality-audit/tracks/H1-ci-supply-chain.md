# Track H1: Red team, CI/CD and supply chain (T-Q18)

> Static, white-box, read-only audit at `AUDIT_SHA = 9fb18cbca26ef305855efc8fc106d896edc82631`. Cites are `path:line` at that SHA. No workflow was run or dispatched, no fork experiment, no push, no secret value read. The only network use was read-only `gh api` GETs of our own repo configuration (`repro/H1/collect_gh_config.sh`, outputs in `repro/H1/gh_api/`, recorded 2026-11-19), including secret **names** (never values) of three environments.

## Critical findings

**None.** No path was found from an *untrusted* actor (fork PR, outside contributor, unapproved first-time contributor) to prod credentials or a prod deploy:

- The repository is **public** (`gh_api/repo.json`), so fork PRs are the untrusted case. Fork `pull_request` runs get no environment secrets and a read-only token; the only fork-reachable jobs are `ci.yml`, `lock-check.yml`, `security.yml` and `terraform.yml` fmt-validate, none of which binds an environment before the `plan` leg (which only runs for same-repo PRs with secrets).
- The single `pull_request_target` workflow (`drill-gate-skip.yml`) checks out the base branch, never PR code, passes PR values only through `env:`, and holds `statuses: write` only. No `workflow_run`, `issue_comment` or `pull_request_review` trigger exists (`repro/H1/workflow_audit.out` §1).
- The prod apply is double-gated: environment `prod` has required reviewers and a custom deployment policy of `branch main` + `tag v*` (`gh_api/prod_branch_policies.json`), `v*` tag creation is restricted to repository admins and tags are immutable (`gh_api/ruleset_tags_*.json`).

**What does exist** is a boundary one step lower: anyone who can push a branch or dispatch a workflow in this repository (the owner, or a stolen token, or an autonomous agent session that holds `git push`) reaches ungated environments that hold prod-grade secrets (H1-01) and can sign images the prod host accepts (H1-02). ADR-0121's own threat model ("single-owner repository, no outside contributors with write access") is the assumption these rest on; they are High, not Critical, under that assumption.

## Summary

| Severity | Count | IDs |
|---|---|---|
| Critical | 0 | none |
| High | 2 | H1-01, H1-02 |
| Medium | 4 | H1-03, H1-04, H1-05, H1-06 |
| Low | 4 | H1-07, H1-08, H1-09, H1-10 |

## 1. Coverage statement

**Read in full:** `.github/workflows/{ci,build,release,rollback,terraform,drill,drill-gate-skip,security,lock-check}.yml`, `.github/workflows/README.md`, `.github/actions/{terraform-env,drill-ssh}/action.yml` (head), `scripts/ci/{drill_gate_skip,ref_guard}.py`, `scripts/ci/tf_env.py` (mapping), `scripts/ci/host_release.py` (ref rules), `terraform/bootstrap/ci/main.tf` (IAM and state-bucket policies), `terraform/modules/bucket_policy/main.tf`, `terraform/modules/compute/user_data.tf` (cosign policy), `terraform/host/agent/bp_agent.py` (config parsing and verify call), `docs/plans/v3/runbooks/{github-settings.md,tailscale-acl.hujson}`, ADR-0100, 0104, 0105, 0121 (and the 0099 / 0111 summaries in the workflow README).

**Read in part (triggers, permissions, environment bindings, `run:` expressions, `uses:`):** `drill-sweeper`, `drill-destroy`, `image-retention`, `key-expiry`, `litestream-plaintext-cleanup`, `restore-drill`, `replace-rehearsal`, `tailnet-cleanup`. Their shell bodies and the scripts `drill_lock.py`, `drill_run_id.py`, `scw_user_data.py`, `litestream_cleanup.py` (gates only) were not reviewed line by line.

**Live config read (GET only):** repo, Actions permissions, fork-PR approval policy, workflow token defaults, environments and their deployment policies, `protect-main` and the two tag rulesets, collaborators, webhooks, deploy keys, repo-level secrets (none), secret names of `prod-plan`, `drill`, `drill-teardown`.

**Checks that came back clean:** every `uses:` is local or 40-hex SHA-pinned, no `docker://`, no reusable workflow from another repo (`workflow_audit.out` §2). `${{ }}` interpolation into `run:` scripts: only three sites, none reachable with attacker-controlled text except H1-08 (`build.yml:133` tags are `sha-*`, `main` or a SemVer tag; `terraform.yml` `inputs.env` is a fixed choice). All dispatch inputs (`tag`, `target`, `drill_run_id`, `ttl_minutes`, `dry_run`) reach shell through `env:` and are validated (`ref_guard.py` regexes, digit regex, integer range). The prod workflows re-check the ref in-job. Cache poisoning: `actions/cache`, `setup-uv`, `setup-node` and buildx `type=gha` caches are written under the PR ref and cannot be read by `main` or a release tag under GitHub's cache scoping (assumption, see Q9). Artifacts: only `coverage-*` and `tfplan-*` (masked text) are uploaded and nothing downloads them across a trust boundary except one `download-artifact` in the restore drill (not reviewed, Q10).

## 2. Goals attempted / not attempted

| Goal | Result |
|---|---|
| Fork or outside PR to secret or deploy | Attempted statically: no path (above). |
| Script injection via `github.event.*` / inputs | Attempted: none found; one PR-file-to-shell path (H1-08). |
| `pull_request_target` / `workflow_run` trust | Attempted: safe pattern confirmed; TOCTOU on the status target (H1-05). |
| Unpinned actions | Attempted: clean. Tool versions inside pinned actions are not pinned (H1-10). Impostor-commit check (does each SHA belong to the upstream tag) **not attempted**: needs reads of third-party repos, outside "our own config". |
| `GITHUB_TOKEN` permissions per job | Attempted: H1-07 (inheritance), H1-02 (`packages: write` from any branch). |
| Environment protection and secret scope | Attempted with live GETs: H1-01, H1-06. |
| `drill-gate` spoofing and skip classifier | Attempted: H1-03, H1-04, H1-05. |
| `scripts/ci/**` inputs to shell | Partly: `ref_guard`, `host_release`, `tf_env`, `drill_gate_skip` read; `drill_lock`, `drill_run_id`, `scw_user_data`, `litestream_cleanup` skimmed only. |
| Terraform IAM of CI credentials | Attempted for `bootstrap/ci` and bucket policies (consistent with ADR-0104/0105; the gap is where the *secrets* live, H1-01). Provider-side IAM state not read. |
| Concurrency-group abuse | Attempted: groups `drill`, `release-prod`, `terraform-<ref>`, `rollback-<env>`. Any branch dispatcher can queue a `drill`-group run and hold the group (a `drill` environment with no reviewers has no approval wait), delaying the sweeper and teardown: availability only, no finding raised. |
| Running workflows, fork experiment, impostor-commit check, repo settings that need admin UI | Not attempted (rules of engagement). |

## 3. Findings

### H1-01 | High | Confirmed | ci-trust-boundary | Ungated, all-branch environments hold prod-grade secrets (prod replica read key, age identity, prod app key, Tailscale OAuth)

- **Location(s):** `.github/workflows/terraform.yml:204-215` (plan job `environment: prod-plan|drill-plan`, runs on same-repo `pull_request`), `terraform.yml:41-56` (`toJSON(secrets)` handed to a **local** composite action `./.github/actions/terraform-env`, i.e. PR-controlled code), `drill.yml:60-107,207-209`, `restore-drill.yml`, `replace-rehearsal.yml` (workflow_dispatch from any ref into `drill`/`drill-teardown`), `scripts/ci/tf_env.py:60-79` (the mapping that exposes them). Live config: `gh_api/environments.json`, `secrets_prod_plan.json`, `secrets_drill_teardown.json`, `secrets_drill.json`.
- **Description:** environments `prod-plan`, `drill`, `drill-plan`, `drill-teardown` have **no reviewers and no deployment-branch policy** (`workflow_audit.out` §4). A job from any branch that names the environment receives its secrets. Workflow YAML and local actions come from the branch itself, so a branch edit (or a PR touching `terraform/**`, which starts the plan leg) runs arbitrary code with them. Their contents (names from the API, meaning from `docs/plans/v3/runbooks/github-settings.md` §2 and ADR-0104):
  - `prod-plan`: `LITESTREAM_AGE_IDENTITY` (prod age identity), `APP_SCW_ACCESS_KEY/SECRET_KEY` (prod app key: read/write/delete on the prod replica bucket policy `bucket_policy/main.tf:9-23`), `GHCR_PULL_PAT`, `TS_OAUTH_*`, plus the read-only `ci-plan` key (which can read the prod **state**, `bootstrap/ci/main.tf:164-171`, and that state embeds the same values).
  - `drill`, `drill-teardown`: `PROD_REPLICA_RO_*` (the prod restore-reader key, `AllowReadOnly` on the prod replica) **and** the prod age identity (`variables.tf:323-325`: "the drill env gets the PROD identity"), `TS_OAUTH_*`, drill CI key, and in `drill` the drill SSH key.
  - Read-reader key + age identity = decrypt the whole prod database (ADR-0078's confidentiality control) from a branch workflow, with no approval and no prod environment involved.
- **Evidence:** `repro/H1/workflow_audit.py` → `workflow_audit.out` §4 and §5 (per environment: gated flag, branch policy, count and names of prod-grade secrets; 5, 8 and 7 for `prod-plan`, `drill`, `drill-teardown`). Contradicted documentation: ADR-0100 §1 "prod-plan ... must not hold a write key" (it holds the prod app key; ADR-0104 accepts that, arguing the state already contains it), ADR-0105 consequences "ci-plan ... gets no access to backup data" (its environment holds the prod age identity and the app key), github-settings runbook §1 ("must hold only the read-only ci-plan key"). The exploit step itself (a branch workflow reading `secrets.*`) is standard GitHub behaviour and was not executed.
- **Impact:** a stolen write-scoped token, a compromised dev machine with push rights, or a prompt-injected autonomous agent (this repo is operated by `git push`-capable agents) can read and decrypt every user's financial data and delete or poison the prod replica without any human approval. Fork PRs cannot (no secrets for forks).
- **Mitigation:** (single best) split by data sensitivity, not by environment name: create `prod-restore-read` (holds only `PROD_REPLICA_RO_*` plus the prod age identity) with required reviewers and `deployment_branch_policy` = `main` only, used only by the restore-drill/gate jobs that really restore prod data; give `prod-plan` and every drill environment a **synthetic** age identity and the drill app key (drill gates restore a synthetic replica, `restore-drill` is the only prod-data consumer); remove `APP_SCW_*` and `LITESTREAM_AGE_*` from `prod-plan` by planning with placeholder values (`TF_VAR_*` dummies, as the PR plan already uses a placeholder image ref). Add a ruleset "restrict workflow edits" is not enough on its own.
- **Alternatives:** keep the secrets but set required reviewers on `drill`/`drill-teardown` and a `main`-only branch policy (cheap, but the operator then approves their own drill gates, and `drill-teardown` must stay ungated for sweeper teardown, so the prod-replica key cannot live there).
- **Effort:** M. **Related:** ADR-0091, 0094, 0100, 0101, 0104, 0105, D Questions H1/H4 item 5, H1-02, H1-06.

### H1-02 | High | Probable | ci-trust-boundary | Prod accepts an image signed by build.yml from any ref; any branch can push and sign `sha-*` images, and rollback resolves mutable tags

- **Location(s):** `terraform/modules/compute/user_data.tf:118` (`identity_regexp = "^https://github\.com/<owner>/<repo>/\.github/workflows/build\.yml@"`, no ref suffix), `terraform/host/agent/bp_agent.py:410-411`, `.github/workflows/build.yml:46-48,97-99,26-29` (`packages: write`, `id-token: write`; `inputs.called` job guard is in the branch's own copy), `drill.yml:149-158` (builds and signs any branch), `rollback.yml:84-92` + `scripts/ci/ref_guard.py:resolve_rollback_target` (accepts `sha-<hex>` or a bare SHA, no ancestry-of-main check), `scripts/ci/host_release.py:resolve_ref` (tag → digest resolved at rollback time).
- **Description:** (1) the host verifies the Sigstore identity only up to the workflow file, so `…/build.yml@refs/heads/attacker/evil-branch` is accepted (`gate_and_signing_probe.out` §2). A branch can run `build.yml` (via `drill.yml`, or edit it and dispatch) with `packages: write` + `id-token: write` and obtain a valid signature over an arbitrary image. (2) GHCR tags are mutable and the token of any branch workflow can push them (package linked with Actions role Write, runbook `image-retention.md`; `image-retention.yml` also dispatches from any ref with `packages: write`). (3) A prod rollback resolves its `target` tag to a digest **at approval time** and the operator's approval screen shows no digest; `sha-<hex>` can name an unmerged branch build (drill gate builds push `sha-<short>` for every branch, `gate_and_signing_probe.out` §5). A release itself is safe: tag and digest come from the same workflow run.
- **Evidence:** regexp acceptance test and rollback-ancestry check in `repro/H1/gate_and_signing_probe.py` → `.out` §2, §5. The package-level settings (who can write the package) were not readable without admin UI, so the end-to-end overwrite is not demonstrated: Probable.
- **Impact:** if an attacker (same trust level as H1-01) overwrites a release tag and an operator later runs "rollback to vX.Y.Z" (or is asked to roll back to a crafted `sha-…`), prod runs attacker code with the prod Litestream and app credentials. Needs one human approval of a legitimate-looking rollback.
- **Mitigation:** (single best) pin the verified identity to the release path: `identity_regexp = ...build\.yml@refs/(heads/main|tags/v[0-9]+\.[0-9]+\.[0-9]+)$` (drill hosts keep a looser pattern via a variable), and make `resolve_rollback_target` accept only tags that were previously applied to prod (read `app_image_previous_ref` / a release list) or whose commit is an ancestor of `origin/main`; additionally print the resolved digest in the job summary before the `prod` approval.
- **Alternatives:** GitHub artifact attestations with `--certificate-github-workflow-ref`; immutable GHCR tags are not available.
- **Effort:** S (regexp) + S (rollback validation). **Related:** ADR-0037, 0099, 0109, 0111, D-10, H4.

### H1-03 | Medium | Confirmed | ci-trust-boundary | The merge gate is self-attested: required checks come from PR-editable workflows, are not bound to an app, and need no review

- **Location(s):** ruleset `protect-main` (`gh_api/ruleset_protect_main.json`): six required contexts without `integration_id`, `required_approving_review_count = 0`, `require_code_owner_review = false`, no bypass actors; no `CODEOWNERS` file; `.github/workflows/drill.yml:262-322` (`gate-result` posts the status, definition lives in the branch), `ci.yml`, `security.yml`, `lock-check.yml` (trigger `pull_request` uses the PR's own workflow files).
- **Description:** `drill-gate-skip.yml` is protected by `pull_request_target`, but the **real** gate is not: `drill.yml` is dispatched from the PR branch and its `gate-result` job is branch code, so a PR that edits it (and `.github/**` always needs the real gate) can post `success` itself. Any workflow with `statuses: write`, or any token with push access, can post the context `drill-gate`, because the rule does not name an app. `just ci`, `pip-audit`, `trivy fs/image` and `uv lock --check` likewise run from the PR's workflow definitions, so the PR can no-op them under the same job names. With zero required approvals and no code owners, the one party that can merge is the PR author. ADR-0121's sentence "a PR cannot edit them to approve itself" is true only for the skip workflow.
- **Evidence:** `repro/H1/gate_and_signing_probe.out` §3 (no `integration_id`, 0 approvals, no CODEOWNERS); `workflow_audit.out` §1.
- **Impact:** the merge gate protects against honest mistakes, not against a compromised or malicious author; a bad change reaches `main` and then a release (which still needs the `prod` approval).
- **Mitigation:** (single best) add a ruleset `workflows` rule ("Require workflows to pass before merging", workflows referenced from `main`) for `ci`, `security`, `lock-check`, and set `integration_id` of the GitHub Actions app (15368) on every required context; add `.github/CODEOWNERS` covering `.github/`, `scripts/ci/`, `terraform/`, `.security-allowlist.yml` and require code-owner review (needs a second human or a bot reviewer account; otherwise this stays accepted risk).
- **Effort:** S. **Related:** ADR-0099, 0121, D Q H1-1.

### H1-04 | Medium | Confirmed | security-control | The skip classifier treats paths as inert that deploy, CI and agent tooling consume

- **Location(s):** `scripts/ci/drill_gate_skip.py:16-37` (`SAFE_DIRS = docs, .claude, tests`; any top-level `*.md`; `LICENSE*`), consumers: `.github/workflows/terraform.yml:140` (`python3 tests/render/render_check.py --require-schema`, part of `fmt-validate`, which `apply` needs), `.github/workflows/litestream-plaintext-cleanup.yml:65` (`docs/plans/v3/runbooks/restore-log.md` decides whether prod plaintext replica objects are deleted), `tests/**` executed by `just ci` inside release.yml, `.claude/**` and top-level `CLAUDE.md` (agent instructions, hooks, skills).
- **Description:** ADR-0121's premise is "the image never copies them". The premise holds for the image, not for the pipeline. A PR changing only `tests/render/render_check.py` (neuter the user-data render and cloud-init schema check), or `restore-log.md` (fake a green restore), or `.claude/settings.json` / `.claude/skills/**` / `CLAUDE.md` (hooks and instructions that every later agent session executes) is classified `skip` and gets `drill-gate = success` with no drill run. This answers D's H1 question 2: yes, a deploy-relevant change can be classified as skip.
- **Evidence:** `repro/H1/classifier_probe.py` → `classifier_probe.out`: cases A-G all print `skip`; the two workflow lines that consume the "inert" paths are printed beneath. Not exploitable: `src/**`, `terraform/**`, `scripts/**`, `.github/**`, `migrations/**`, `Dockerfile`, `pyproject.toml`, `uv.lock`, traversal and empty lists all print `gate`. Robustness note: `./src/x.md` and `SRC/x.md` print `skip` (GitHub never emits either form, so unreachable).
- **Impact:** a docs/tests-only PR can weaken a deploy gate or steer the agents that author the next PRs without ever being drilled.
- **Mitigation:** (single best) shrink the allowlist to what nothing executes: `docs/**` except `docs/plans/v3/runbooks/restore-log.md`, top-level `*.md` except `CLAUDE.md`, drop `.claude/` and `tests/render/` and `tests/` entirely (tests are cheap to drill) or add `tests/` back only when the drill-relevant subtrees are excluded; add a unit test that greps `.github/` and `scripts/ci/` for paths under allowlisted dirs and fails when one is referenced.
- **Effort:** S. **Related:** ADR-0121, ADR-0112, H1-05.

### H1-05 | Medium | Probable | ci-trust-boundary | drill-gate-skip verdict and status target come from two different moments (TOCTOU)

- **Location(s):** `.github/workflows/drill-gate-skip.yml:55-60` (file list from live `pulls/${PR}/files`), `:88` (status on the event's `pull_request.head.sha`), `:23-25` (`cancel-in-progress` per PR).
- **Description:** the classification is computed from the PR's current file list but posted on the SHA captured in the event payload, and nothing compares the two. Sequence: commit A (deploy-relevant) is pushed, then a docs-only commit B replaces the head quickly (force-push) or the files API lags behind the new head. A run started for A that lists B's (or the stale earlier) files posts `success` on A's SHA; statuses persist per SHA, so re-pushing A (or using A as the head) is already green. `pulls/N/files` is eventually consistent after a push, so the stale-list variant needs no attacker, only bad timing.
- **Evidence:** `repro/H1/gate_and_signing_probe.out` §1 (list source `pulls/${PR}/files`, target `github.event.pull_request.head.sha`, no head comparison). The race itself was not reproduced (no workflow runs allowed): Probable.
- **Impact:** a deploy-relevant head SHA can carry a `skip` success without a drill.
- **Mitigation:** list files from the exact commit range (`gh api repos/$REPO/compare/${BASE_SHA}...${HEAD_SHA} --jq '.files[]...'` with the event's two SHAs) and, before posting, re-read `pulls/$PR --jq .head.sha` and refuse if it differs from `$SHA`.
- **Effort:** S. **Related:** ADR-0121, H1-04.

### H1-06 | Medium | Probable | infra-exposure | The Tailscale OAuth secret in ungated environments can mint `tag:ci`, which the ACL lets reach prod sshd

- **Location(s):** `docs/plans/v3/runbooks/tailscale-acl.hujson` (`tag:automation` owns `tag:prod`, `tag:drill`, `tag:ci`; rule `src tag:ci → dst tag:prod:22`), `TS_OAUTH_SECRET` in `prod-plan`, `drill`, `drill-teardown` (`gh_api/secrets_*.json`), `drill.yml:213-218`, `terraform.yml:337-345` (`tailscale/github-action` with `tags: tag:ci`).
- **Description:** every environment holds the `budget-planner-automation` client (`auth_keys` write). Whoever runs a branch workflow with it joins the tailnet as `tag:ci`. The (intended) ACL then allows `tag:ci → tag:prod:22`, a leftover of the SSH deploy path that ADR-0111 removed ("There is no SSH deploy path"); no workflow SSHes to prod any more. Reaching port 22 still needs the operator's private key, so this is exposure of sshd to a key-holder boundary, plus it also reaches drill SSH/443.
- **Evidence:** config citation; the live ACL in the Tailscale admin console was not readable (Q6).
- **Impact:** removes the network layer between a branch workflow and the prod host; any sshd weakness or leaked operator key becomes reachable from CI.
- **Mitigation:** delete the `tag:ci → tag:prod:22` rule (nothing needs it), keep `tag:ci → tag:drill:{22,443}`, and move the OAuth client of `prod-plan` out (plans do not join the tailnet; the Tailscale provider only needs it at apply, which runs in `prod`).
- **Effort:** S. **Related:** ADR-0094, 0101, 0111, H1-01, H4.

### H1-07 | Low | Confirmed | ci-trust-boundary | The release `ci` job runs tests and third-party installers with `packages: write`, `id-token: write`, `pull-requests: write`

- **Location(s):** `.github/workflows/release.yml:27-31,76-79`, `.github/workflows/ci.yml:16-86` (no `permissions:` block).
- **Description:** a called workflow without its own `permissions` inherits the caller's top-level grant. `ci.yml` run under release therefore executes `npm ci`, `uv sync`, `uv python install`, `setup-uv version: latest` and the whole `tests/` tree with an `id-token`-capable, package-writing token, where read-only suffices (`drill.yml` is read-only at the top so the drill path is fine).
- **Evidence:** `gate_and_signing_probe.out` §4. **Impact:** a compromised npm/PyPI dependency during a release could push to GHCR (unsigned, so the host would refuse it, but it can overwrite tags that rollback resolves, H1-02) or request OIDC tokens. **Mitigation:** add `permissions: contents: read` to `ci.yml` and to the `ci` job of `release.yml`; drop top-level `pull-requests: write` and `packages: write` from `release.yml` (grant them per job). **Effort:** S. **Related:** H1-02.

### H1-08 | Low | Confirmed | ci-trust-boundary | `.security-allowlist.yml` is read from the PR checkout and its values reach a `run:` line and `GITHUB_OUTPUT` unescaped

- **Location(s):** `.github/workflows/security.yml:62-74` (builds `ignore_args`), `:75` (`${{ steps.allowlist.outputs.ignore_args }}` interpolated into `run:`), `.security-allowlist.yml`.
- **Description:** answers D's H1 question 1. A PR can add any `pip_audit: - cve:` entry and the required check `pip-audit (uv.lock)` passes; a crafted `cve` value injects shell into the job (and a newline injects extra `GITHUB_OUTPUT` keys). The job has `contents: read` and no secrets, and the same PR could simply edit `security.yml` (H1-03), so this is a hygiene finding; it matters because fork PRs also run this job.
- **Evidence:** `repro/H1/allowlist_injection.py` → `.out`: the benign ignore, `X; echo INJECTED-$(id -un)` appearing verbatim in the shell line, and `evil=1` as a second output line.
- **Mitigation:** pass the list through `env:` and a validated bash array (`[[ $cve =~ ^[A-Za-z0-9-]+$ ]]`), and read the allowlist from `origin/main` (`git show origin/main:.security-allowlist.yml`) so a PR cannot widen it in the same PR. **Effort:** S. **Related:** H1-03, D §3.

### H1-09 | Low | Confirmed | config-drift | Repository Actions settings are weaker than the runbook states

- **Location(s):** `gh_api/actions_permissions.json` (`allowed_actions: all`, `sha_pinning_required: false`), `gh_api/actions_fork_pr.json` (`first_time_contributors`), `gh_api/environments.json` (`prod`: `prevent_self_review: false`, `can_admins_bypass: true`), `gh_api/branch_protection_main.json` (404, the ruleset is used instead), `docs/plans/v3/runbooks/github-settings.md` §1/§5 (unticked boxes: restrict actions, require SHA pinning, fork approval for all outside collaborators).
- **Description:** pinning is currently by convention only; one unpinned `uses:` would pass review and run. Fork PR approval is only for first-time contributors, so a second PR from a previously merged contributor runs without approval (still without secrets). Sole `prod` reviewer is the author (accepted, single-owner).
- **Mitigation:** set `sha_pinning_required: true` and `allowed_actions: selected` (GitHub-owned + the nine pinned third parties), fork approval to "all outside collaborators"; add a test over `.github/**/*.yml` that every `uses:` is a SHA. **Effort:** S. **Related:** ADR-0099, github-settings runbook.

### H1-10 | Low | Confirmed | dependency | Tool versions installed by pinned actions float, and the workflow README lists a workflow that does not exist

- **Location(s):** `ci.yml:25` (`setup-uv` `version: "latest"`), `security.yml:50,111,126` (`setup-uv` with no version, trivy via the action default), `terraform.yml:135-137` (`apt-get install cloud-init` unpinned), `drill.yml:213`/`terraform.yml:337` (`tailscale/github-action` default client version), `.github/workflows/README.md` (row `uptime.yml`, no such file at `AUDIT_SHA`).
- **Description:** a pinned action SHA does not pin what it downloads; `uv` and tailscale are fetched as "latest" on every release and drill. Unpinned tooling in the release path is a small, real supply-chain surface (D-10 covers the Docker side). **Mitigation:** pin `uv`, tailscale and `cloud-init` versions (checksums where the action supports them) and add `uptime.yml` or remove the README row. **Effort:** S. **Related:** D-10.

## 4. Questions for the operator (settings and facts that could not be read)

1. **Q1 (H1-01):** are the values in `prod-plan` really the prod age identity and prod app key (per runbook §2), or placeholders? If real, rotate them after remediation.
2. **Q2 (H1-01):** do the drill gate runs restore **prod** replica data (they receive `PROD_REPLICA_RO_*` and the prod age identity), or does only `restore-drill.yml` need that? If only the latter, the drill environments can lose both secrets.
3. **Q3 (H1-02):** package settings of `ghcr.io/mtkublin/budget-planner`: which repositories/actors have Write, is the Actions role Write (runbook says so), and are `vX.Y.Z` tags protected? Also: has a rollback ever been run to a `sha-*` tag?
4. **Q4 (H1-03):** is a second reviewer or bot account feasible for code-owner review, or is the self-approved merge the intended steady state (then record H1-03 as accepted risk)?
5. **Q5 (H1-05):** has `drill-gate-skip` ever posted on a SHA that was not the PR head at run time? Check run logs for `synchronize` bursts.
6. **Q6 (H1-06):** is the live Tailscale ACL identical to `tailscale-acl.hujson` (in particular `tag:ci → tag:prod:22`) and is Tailscale SSH enabled on prod?
7. **Q7:** the `release` run history: were any `release.yml` runs dispatched from a non-tag ref (they fail at `guard`, but are they logged as attempts)?
8. **Q8:** does any bot (Dependabot, Renovate, Copilot) or deploy key/PAT hold write access? `collaborators.json`, `deploy_keys.json`, `hooks.json` show only the owner, no keys, no hooks; PATs are not visible via the API.
9. **Q9 (cache boundary):** confirm no workflow on `main`/tag restores a cache key that a PR-ref job can also write (default scoping should prevent it; not verified by a run).
10. **Q10:** the `download-artifact` use in `restore-drill.yml` (not reviewed) and the shell bodies of `drill_lock.py`, `scw_user_data.py` are worth a second pass by H4 or a later audit.

## 5. Repro index (`docs/plans/quality-audit/repro/H1/`)

| File | Proves | Recorded output |
|---|---|---|
| `collect_gh_config.sh` | read-only GETs of repo, Actions, environments, rulesets, secret names | `gh_api/*.json` |
| `workflow_audit.py` | triggers, pinning, `run:` interpolation, env/protection/secrets table (H1-01, H1-06, H1-09) | `workflow_audit.out` |
| `classifier_probe.py` | skip verdicts for crafted file lists and the consumers of inert paths (H1-04) | `classifier_probe.out` |
| `allowlist_injection.py` | PR-controlled allowlist to shell and output injection (H1-08) | `allowlist_injection.out` |
| `gate_and_signing_probe.py` | TOCTOU inputs, cosign identity acceptance, ruleset gaps, permission inheritance, rollback validation (H1-02, 03, 05, 07) | `gate_and_signing_probe.out` |

Note on `workflow_audit.out` §4: the job→environment map over-approximates `terraform.yml:plan/apply` (matrix and `inputs.env` expressions are listed under both `prod` and `drill`; the plan leg really binds `prod-plan`/`drill-plan`). §5 is computed from the recorded secret names and is exact.
