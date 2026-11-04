# ADR-0084: v3 Compute Zone `pl-waw-2` and Ubuntu 24.04 (`ubuntu_noble`) Image Slug

- **Status**: Accepted
- **Date**: 2026-11-04
- **Amends**: [ADR-0032](0032-v3-remote-deployment-scaleway-stardust-warsaw.md) §Decision and "Region / zone"
- **Related**: [ADR-0035](0035-v3-infrastructure-as-code-terraform.md) (Terraform owns the instance), operator checklist decision D1, T-D24 (compute module), T-D25 / T-D27 (first applies), T-D62 (this change)

## Context

1. ADR-0032 puts the instance in zone `pl-waw-1`. On 2026-11-03 the operator found Stardust1-S **sold out in `pl-waw-1`** and available in `pl-waw-2` (operator checklist, decision D1).
2. ADR-0032 and ADR-0035 specify **Ubuntu 24.04 LTS**. The compute module's `image` default is `ubuntu_jammy`, the Scaleway marketplace slug for Ubuntu **22.04**, even though its description says 24.04. Every `terraform apply` would boot 22.04.
3. The Scaleway console also offers InstantApps, such as a Docker image. They are not an option here. Cloud-init (`bootstrap.yaml.tpl`) installs Docker from Ubuntu's archive (`docker.io`, `docker-compose-v2`), and those packages conflict with the upstream `docker-ce` / `containerd.io` packages that come preinstalled on the Docker InstantApp. The InstantApp's base release is also set by Scaleway, not by us.

## Decision

- **Zone**: `pl-waw-2`. The region stays `pl-waw`, so Object Storage (Litestream replica, Terraform state bucket) is unaffected, because buckets are regional. `scaleway_zone` stays a Terraform variable. The default and both `envs/*/terraform.tfvars.example` files say `pl-waw-2`, and so does `SCW_DEFAULT_ZONE` in `.github/workflows/restore-drill.yml`.
- **Image**: `ubuntu_noble` (Ubuntu 24.04 LTS) is the compute module default. Plain marketplace Ubuntu only. No InstantApps.
- **Stock moves.** The operator re-checks Stardust availability in the chosen zone right before T-D25 (first drill apply) and T-D27 (first prod apply). If `pl-waw-2` sells out, switch by overriding `scaleway_zone` in tfvars. That needs no code change, only a note in the operator checklist.

## Consequences

- Drill and prod both land in `pl-waw-2`. Moving to another zone later is a rebuild plus a Litestream restore, the same path as disaster recovery (RTO < 60 min, ADR-0032).
- The first apply boots 24.04, which the cloud-init packages (`docker-compose-v2`, unattended-upgrades configuration) are written for.
- If the zone ever has to change mid-life, the instance and flexible IPs are zonal and are recreated. DNS follows via `module.dns`.
