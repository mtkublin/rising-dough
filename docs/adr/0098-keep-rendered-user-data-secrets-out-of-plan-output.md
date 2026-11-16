# ADR-0098: Keep Rendered User-Data Secrets Out of Plan Output

- **Status**: Accepted
- **Date**: 2026-11-07
- **Relates to**: ADR-0032, ADR-0035, ADR-0092, ADR-0093, ADR-0094, ADR-0097

## Context

The Scaleway instance's `cloud_init` embeds the age identity, Tailscale auth key, Litestream S3 keys, GHCR PAT, cookie secret and admin password (T-D83). A real drill plan (2026-11-07, provider `~> 2.46`, Terraform 1.17.1) showed:

- On create, `cloud_init = (sensitive value)`, because every input variable is sensitive.
- On `-replace` of the server and on an in-place update, the plan printed the **old** `cloud_init` from state in plain text, including `AGE-SECRET-KEY-1...` and `tskey-auth-...`. The provider schema does not mark `cloud_init` sensitive and the state held no `sensitive_attributes` entry for it, so the prior value had no mark.
- `.github/workflows/terraform.yml` posts plans to PR comments and logs, so a prod plan would publish prod secrets.

Separate finding: changing `cloud_init` alone plans `scaleway_instance_server.app will be updated in-place`. cloud-init runs once per instance, so an in-place update only rewrites the stored value; the VM never re-runs it.

## Decision

1. **(a) `cloud_init = sensitive(local.user_data)`** in the compute module. The compute `user_data` output was already `sensitive = true` (T-D77). With the mark on the config value, Terraform records `sensitive_attributes` for `cloud_init` in state when the resource is next written, so later plans mask the prior value too. A `terraform test` run (`command = plan`) asserts the server's `cloud_init` is sensitive via `issensitive()` (compute output `cloud_init_is_sensitive`) and that `output.user_data` is sensitive. Note: input variables are already sensitive, so the plan-time assertion does not by itself prove the state fix; the state-side effect is documented and verified on the first real apply.
2. **(c) Belt and braces in CI and locally.** `terraform/scripts/mask_plan.py` (stdlib only, unit-tested) replaces `AGE-SECRET-KEY-1...`, `tskey-...`, `ghp_...`, `github_pat_...` and `SCW<17>` with `***`. `terraform.yml` pipes every `plan`, `show` and `apply` output through it. A step emits `::add-mask::` for the secret inputs (GitHub secrets are masked already; this also covers each line of the multi-line age identity). Secrets minted inside Terraform (Tailscale key, IAM keys) are covered by the patterns only. The plan artifact no longer uploads `plan.bin`, whose binary form embeds raw config and state values. `just tf-plan-safe <env>` does the same locally.
3. **Runbooks**: a user-data change takes effect only with `-replace=module.compute.scaleway_instance_server.app` (this recreates the VM; data restores from Litestream). An in-place plan on `cloud_init` is a no-op for the host.

### Operator action on the first apply after this fix

State written by earlier applies lacks the sensitive mark, so the first plan/apply that touches the server may print the old `cloud_init` once. Always run it through the mask: `just tf-plan-safe <env>`, or `terraform apply ... | python3 terraform/scripts/mask_plan.py`. That apply rewrites the attribute and records `sensitive_attributes`; later plans are masked natively. `terraform apply -refresh-only` alone is not enough: refresh does not re-evaluate config marks. Do not paste an unmasked drill or prod plan into chat, issues or PRs; if one was already posted, rotate the exposed secrets.

### Future hardening (b), not done

Stop passing secrets in user-data: fetch them at boot from a secret manager (Scaleway Secret Manager with a scoped IAM key, or Tailscale-delivered), keeping only a bootstrap credential in user-data. Larger change; it also removes secrets from the instance metadata API and from Terraform state.

## Consequences

- Plans and applies are safe to log; masking is defence in depth, not the primary control.
- Random secrets (cookie secret, admin password) have no recognisable shape and rely on `sensitive()`.
- The `plan.bin` artifact is gone; `plan.txt` (masked) remains.

## Amendment 2026-11-07 (T-D85)

The first plan after T-D83 printed the PRIOR state value of `user_data["cloud-init"]` as a removal block (`- "cloud-init" = <<-EOT ...`). Pattern masking missed random values (admin password, cookie secret, UUID-format Scaleway secret keys), so they appeared in clear text. This can recur whenever a prior value of a rendered template shows up in plan output.

`mask_plan.py` now additionally (1) redacts the whole body of any heredoc opened by a `cloud-init` / `cloud_init` / `user_data` / `user-data` key (any `+`/`-`/`~` marker, quoted or not, any delimiter word), replacing it with one `(redacted by mask_plan.py: N lines)` line while keeping the opening and closing delimiter lines; an unterminated heredoc is redacted to EOF; and (2) masks values of YAML/env/HCL keys whose name contains PASSWORD, SECRET, TOKEN, AUTHKEY or IDENTITY, or ends in `_KEY`, as defence in depth outside heredocs. Other heredocs (e.g. policy JSON) are untouched. No new decision; the filter remains secondary to `sensitive()`.
