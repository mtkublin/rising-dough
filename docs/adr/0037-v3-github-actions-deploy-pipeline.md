# ADR-0037: v3 Deployment Pipeline — GitHub Actions SSH Deploy with Immutable Image Tags

- **Status**: Proposed
- **Date**: 2026-10-27 (renumbered v2 → v3 on 2026-10-28)
- **Related**: ADR-0018 (CI matrix), ADR-0032 (v3 remote deployment), ADR-0035 (Terraform), ADR-0034 (Litestream)

## Context

Deploys must be:

- **Automated**: a push to `main` lands in production without a human running shell commands.
- **Reproducible**: every live image maps to a specific git SHA, pullable long after the deploy.
- **Reversible**: rollback is a single command executed by the pipeline or by the operator.
- **Observable**: a failing deploy is visible before it reaches live traffic; a succeeding deploy is announced.
- **Safe**: deploys do not require shelling into the VM manually; the deploy user cannot run arbitrary commands.

ADR-0018 established the CI matrix. ADR-0032 established what the deploy target looks like. This ADR specifies how the CI image gets onto the running Stardust instance.

## Decision

### 1. Pipeline topology

```
PR → ci.yml  (test + lint + typecheck)
     │
     └── on merge to main
         ▼
     build.yml  (docker build + push to GHCR with SHA + :main tags)
         │
         └── on build success + manual approval of `prod` env
             ▼
         deploy.yml  (SSH + docker compose pull + up -d + health probe)
             │
             └── on failure
                 ▼
             rollback step (reverts to previous image tag)
```

Three workflows, three concerns:

- `.github/workflows/ci.yml` — unchanged from v1 (`just ci`). Runs on PRs and pushes.
- `.github/workflows/build.yml` — on push to `main` with CI green, builds a multi-arch (`linux/amd64` only in v3) Docker image, pushes to `ghcr.io/<owner>/budget-planner` tagged `:sha-<short>`, `:main`, and (on release tag) `:vX.Y.Z`.
- `.github/workflows/deploy.yml` — on `build.yml` success, requires manual approval of the GitHub Actions environment named `prod`. Deploys via SSH.

### 2. Image tagging

- `:sha-<short>` — immutable, every build. Used by the deploy pipeline.
- `:main` — rolling tag pointing at the latest green `main`. **Not used by the pipeline** (would be racy); only exists for diagnostics and manual pulls.
- `:vX.Y.Z` — on git tag push matching `^v[0-9]+\.[0-9]+\.[0-9]+$`.
- Images are **signed with cosign** using a GitHub OIDC-issued keyless signature. Deploy step verifies the signature before `docker compose up`.

### 3. Deploy user and SSH command restriction

On the Scaleway VM (provisioned by Terraform cloud-init):

- A dedicated user `deploy` with no shell (`/usr/sbin/nologin`) and a single SSH key allow-listed via `authorized_keys`:

  ```
  command="/usr/local/bin/deploy-budget-planner",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA...<github-actions-pubkey>
  ```

- `/usr/local/bin/deploy-budget-planner` (rendered by cloud-init):

  ```bash
  #!/usr/bin/env bash
  set -euo pipefail

  # SSH_ORIGINAL_COMMAND format: "deploy sha-abc1234" or "rollback"
  read -ra ARGS <<<"${SSH_ORIGINAL_COMMAND:-}"

  cd /etc/budget-planner

  case "${ARGS[0]:-}" in
    deploy)
      TAG="${ARGS[1]:?missing image tag}"
      # Validate tag format.
      [[ "$TAG" =~ ^sha-[0-9a-f]{7,40}$|^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "bad tag" >&2; exit 2; }
      cosign verify --certificate-identity-regexp '^https://github.com/<owner>/budget-planner/' --certificate-oidc-issuer https://token.actions.githubusercontent.com ghcr.io/<owner>/budget-planner:$TAG
      PREV_TAG=$(docker inspect --format='{{index .Config.Labels "org.opencontainers.image.revision"}}' budget-planner-app-1 2>/dev/null || echo "")
      echo "$PREV_TAG" > .previous-tag
      TAG="$TAG" docker compose pull app
      TAG="$TAG" docker compose up -d app
      # Post-deploy health probe (30s budget).
      for i in $(seq 1 30); do
        curl -fsS https://localhost/ready --resolve localhost:443:127.0.0.1 -k && exit 0
        sleep 1
      done
      echo "post-deploy /ready failed, rolling back" >&2
      TAG="$PREV_TAG" docker compose up -d app
      exit 3
      ;;
    rollback)
      PREV=$(cat .previous-tag)
      [[ -n "$PREV" ]] || { echo "no previous tag recorded" >&2; exit 4; }
      TAG="$PREV" docker compose up -d app
      ;;
    *)
      echo "usage: deploy <tag> | rollback" >&2
      exit 1
      ;;
  esac
  ```

- The GitHub Actions deploy step runs `ssh deploy@<host> "deploy sha-$GITHUB_SHA_SHORT"`.
- The deploy user cannot run anything else. If the operator needs a shell, they use their personal SSH key against the `app` user (separate from the deploy user).

### 4. Secrets

GitHub Actions encrypted secrets (environment-scoped to `prod`):

- `DEPLOY_SSH_PRIVATE_KEY` — ed25519 private key paired with the public key allow-listed above. CI only.
- `DEPLOY_HOST` — e.g. `budget.<domain>`.
- `GHCR_PAT` — a GitHub PAT with `read:packages` for pulling private images from the VM (cloud-init writes this into `/etc/docker/config.json` at bootstrap).

**No** secrets are kept on the VM beyond what cloud-init renders. The VM does not have a Scaleway API key capable of mutating infrastructure — only the Litestream-scoped IAM key for object-storage I/O (ADR-0035 §6).

### 5. Rollback

- Automatic on `/ready` probe failure within the deploy script (section 3).
- Manual: `ssh deploy@<host> "rollback"` from the operator's workstation or from a manual GitHub Actions workflow dispatch of `rollback.yml` with no inputs. Uses the recorded `.previous-tag` file.
- The pipeline keeps the previous two SHAs runnable (image layers remain in Docker's local cache; GHCR retains them indefinitely as untagged until manual GC).

### 6. Pre-deploy gates

- CI (`just ci`) green.
- Image signature verified by cosign.
- `/ready` probe green within 30 s.

Failure of any gate blocks the deploy and leaves the previous version running.

### 7. Observability of the deploy

- Deploy workflow posts a GitHub Deployment status (`in_progress` → `success` | `failure`).
- Deployment history is visible under the `prod` environment in GitHub.
- On success: step summary includes the deployed SHA + a link to the compare view against the previous SHA.
- On failure: step summary includes the probe response and the first 50 lines of `docker compose logs app --tail 50`.

## Consequences

### Positive

- One click per deploy (environment approval).
- Rollback is a single SSH command.
- Deploy user is tightly caged — no shell, no port forwarding, no arbitrary commands.
- Immutable SHA-tagged images make rollback and investigation deterministic.
- cosign signature verification prevents a compromised GHCR account from pushing poisoned images.

### Negative

- Requires a `prod` environment approval, which is a human step. This is deliberate (ADR-0032 single-user, operator-is-user); if the user prefers full automation, this ADR can be amended to drop the approval gate for `main` and keep it for `vX.Y.Z` tags.
- Keeping the deploy SSH key in GitHub Actions means a GitHub takeover implies a prod takeover. Mitigation: branch protection + required reviews on `.github/workflows/deploy.yml` and 2FA on the GitHub account.
- Health probe is HTTP-level only. Deeper probes (login, DB write round-trip) are run in Phase 4 as part of the acceptance smoke suite, not in-pipeline.

### Follow-ups

- A later ADR may replace SSH deploy with pull-based deploy (the VM polls GHCR for a new tag and self-updates). Reduces the GitHub Actions key surface at the cost of a few minutes of deploy latency.
- A later ADR may add staging on a cheaper or spot instance if the app grows enough to warrant pre-prod testing beyond local docker-compose.

## Alternatives Considered

- **Pull-based self-update on the VM** — simpler key surface but delays deploys and complicates rollback coordination. Deferred.
- **Scaleway Container Registry + Scaleway Serverless Containers** — bypasses the VM entirely, but reintroduces the Cloud Run-style ephemeral FS problem (ADR-0032 §Alternatives).
- **ArgoCD / Flux** — massive overkill for one app on one host.
- **Direct `scp` of a tarball + systemd restart** — rejected; image-based deploys are more reproducible and let the local docker-compose smoke test map 1:1 to prod.

## Amendment 2026-11-07 (T-D95)

Superseded in part by ADR-0099 (2026-11-07): the drill→prod workflow_run chain is replaced by release.yml; drill is validated pre-merge.
