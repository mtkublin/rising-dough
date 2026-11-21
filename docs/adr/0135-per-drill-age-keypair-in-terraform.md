# ADR-0135: Per-Drill Litestream Age Key Pair Generated in Terraform

- **Status**: Accepted (T-Q277). The GitHub settings half (deleting now-unused secrets) is the operator's.
- **Date**: 2026-11-21
- **Amends**: [ADR-0132](0132-ci-environments-split-by-data-sensitivity.md) (decisions 3 and 4: drill environments hold no age key at all, not a synthetic pair), [ADR-0078](0078-v3-data-protection-quick-wins.md) section 3 (who owns which age key)
- **Relates to**: [ADR-0093](0093-ci-terraform-inputs-via-tf-var-environment-secrets.md), [ADR-0101](0101-drill-environment-is-tailnet-only.md), [ADR-0111](0111-terraform-declared-host-state.md), [ADR-0114](0114-litestream-replicate-identity-and-forced-generation.md)
- **Finding**: Q-012 (H4-03); task T-Q277; operator decision 2026-11-21

## Context

One input pair, `litestream_age_identity` / `litestream_age_recipient`, did two jobs:

1. **Own replica**: the host encrypts its Litestream replica to the recipient and, after a VM replacement, decrypts it again with the identity.
2. **Prod replica read**: in the restore drill (`--restore-source`) the same identity decrypts the **prod** replica.

ADR-0132 kept the pair in the drill environments as a "synthetic" value. That still leaves a long-lived, shared secret in ungated environments, and a shared key means one drill can read every other drill's replica. The replacement rehearsal (`replace-rehearsal.yml`) replaces a drill's VM and restores **that drill's own** replica on the new VM, so the drill key must outlive the VM: it cannot be generated on the host.

## Decision

1. **Split the two roles.**
   - *Own replica key pair.* On `env == "drill"` it is a Terraform resource, `age_secret_key.drill` (count 1), and `main.tf` selects it through `local.litestream_age_identity` / `_recipient`. On prod it is the operator-held pair from the `prod` environment, as before.
   - *Prod replica identity for the restore drill.* A new input `restore_source_age_identity`, supplied by `tf_env.py --restore-source` from `prod-restore-read`'s `LITESTREAM_AGE_IDENTITY`, rendered to `restore-source-age.key` (0600) and read by `restore-from-prod`, only when `enable_restore_helper` (ADR-0132 decision 4). The host's own `litestream-age.key` is never the prod identity.
2. **Inputs are env-conditional, not unconditionally required.** `litestream_age_identity` / `_recipient` default to `""`; validation requires the regex match when `env == "prod"` and requires empty when `env == "drill"`. `restore_source_age_identity` is empty or valid, and drill-only. `tf_env.py` emits the first two for prod only. `preflight.py` checks them for prod only.
3. **Drill environments hold no age key.** `drill`, `drill-plan`, `drill-teardown` need no `LITESTREAM_AGE_*`. `prod-plan` keeps its placeholder pair (a prod plan still validates them). `prod-restore-read` keeps the prod `LITESTREAM_AGE_IDENTITY` only (the recipient is no longer read there).
4. **Lifecycle.** The pair lives in the drill's own Terraform state: a VM replacement keeps it (the replacement rehearsal restores with it), a new drill (new state, new bucket) gets a new pair, a teardown destroys it. No rotation procedure exists or is needed for drills.
5. **Root lock file is committed.** `terraform/.gitignore` no longer ignores `/.terraform.lock.hcl`. It pins every root provider (scaleway, tailscale, random, age) with hashes for `linux_amd64` (CI) and `darwin_arm64` (operator laptop), generated with `terraform providers lock -platform=linux_amd64 -platform=darwin_arm64`. Side effect, accepted: scaleway/tailscale/random are now pinned by hash as well, and move only by an explicit `terraform init -upgrade` plus lock commit.

## Supply chain: the age provider

| | |
|---|---|
| Source | `registry.terraform.io/koendelaat/age` (repository `github.com/koendelaat/terraform-provider-age`) |
| Version | exactly `= 0.1.3` (released 2024-04-26; the only later push is repository maintenance, 2024-12-18) |
| License | MPL-2.0 |
| Maintainer | `koendelaat`, a maintained fork of `clementblaise/age` (last release 0.1.1, 2022-02-16, abandoned). Single maintainer, low download count (about 2.2k vs 844k for the original) |
| Dependencies | `filippo.io/age` v1.2.0 (the reference age implementation), `terraform-plugin-sdk/v2` v2.34.0, Go 1.21 |
| What it does with keys | One resource, `age_secret_key`: generates an X25519 identity with `filippo.io/age` and exposes `secret_key` (sensitive) and `public_key`. No provider configuration, no data sources, no network access by design (small enough to read in full before bumping the pin) |

Why this one: the other candidates are `clementblaise/age` (abandoned, 2022, age v1.0.0 and SDK v2.10) and `meallia/sopsage` (active, but its registry docs list no key-generation resource, and it pulls in the whole sops dependency tree for a one-resource need). `koendelaat/age` is the newest release with a current age library and the smallest surface.

Why not `data "external"`: it would execute a script or binary (`age-keygen`) on the CI runner at plan time. That adds an unpinned, unsigned executable to the runner path, re-runs on every plan (a data source has no state, so the key would change each time unless it is wrapped in a resource), and cannot be hash-locked. A provider resource is generated once, kept in state, and hash-pinned in `.terraform.lock.hcl`.

Mitigations for the single-maintainer risk: exact version pin plus lock hashes (no silent update); the keys protect a **drill** replica holding anonymised or restored-drill data, never the prod replica key; the generated recipient and identity are checked by the same regexes the host expects (a malformed output fails the restore guard, not silently); a bump needs an explicit lock regeneration reviewed in a PR (CODEOWNERS covers `terraform/`).

## Consequences

- **Accepted residual: key material lands in the drill's Terraform state.** The state is encrypted at rest in the drill state bucket (ADR-0035), and reading it needs the drill CI key (the `drill` environment). That is the same trust boundary that already covers the drill's other generated secrets (`random_password` admin and cookie values, the Tailscale auth key). The drill key protects only that drill's replica; a leak exposes nothing of prod.
- The drill state's age key and the drill replica share a lifetime; `terraform destroy` of the drill makes its replica undecryptable, which is the intent.
- `check_tf_vars.py` no longer lists the age pair as required (it has a default); the prod requirement is enforced by the variable validation (a prod plan without a valid pair fails at plan time with a named error).
- Documented operator step after merge: delete `LITESTREAM_AGE_IDENTITY` and `LITESTREAM_AGE_RECIPIENT` from `drill`, `drill-plan`, `drill-teardown`; no other environment changes. The runbooks `github-settings.md` and `key-rotation.md` are updated.
- Tests: `terraform test` covers drill generation without any age input, rejection of supplied drill age inputs, prod requiring and validating the pair, and the restore-source identity reaching the host only with the restore helper.
