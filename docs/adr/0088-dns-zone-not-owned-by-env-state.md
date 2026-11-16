# ADR-0088: DNS Zone Is Not Owned by Any Env Terraform State

- **Status**: Accepted
- **Date**: 2026-11-06
- **Amends**: [ADR-0035](0035-v3-infrastructure-as-code-terraform.md) (resource table row "DNS zone", `modules/dns`)
- **Related**: [ADR-0084](0084-v3-compute-zone-pl-waw-2-and-ubuntu-noble-image.md), operator checklist decision D2, T-D22 (dns module), T-D25 / T-D26 / T-D41 (drill apply, teardown, monthly restore drill), T-D63 (this change)

## Context

1. `modules/dns` (T-D22) created `scaleway_domain_zone` (`subdomain = ""`) for the whole domain in each env state when `managed_zone = true`. Drill and prod are separate states, so two states would own one zone. `terraform destroy` on drill (T-D26, and the monthly automated restore drill T-D41) could delete the zone and with it the prod records.
2. `rising-dough.eu` was bought through Scaleway Domains on 2026-11-04. Its root zone already exists at Scaleway.
3. Provider docs (`scaleway/scaleway` registry, `~> 2.46` as pinned in `modules/dns/versions.tf`; checked 2026-11-06 via the provider's `docs/resources/domain_zone.md` and `docs/data-sources/domain_zone.md`): `scaleway_domain_zone` "creates a DNS zone for a **subdomain** of a domain you already own". `domain` and `subdomain` are both Required, and the example creates `test.scaleway-terraform.com`. The resource is meant for child zones, not for the root zone that registration creates. An empty `subdomain` for an existing root zone is undocumented and would at best collide with it, at worst import and then delete it on destroy. The data source has the same required arguments and no documented root-zone form.
4. `scaleway_domain_record.dns_zone` takes the zone name as a plain string. A record does not need a zone resource in state.

## Decision

- **No env state creates or owns the zone.** `scaleway_domain_zone` is removed from `modules/dns`. No data source either, because of point 3 (nothing documented for an empty subdomain).
- **Records reference the zone by name.** `scaleway_domain_record.a` / `.aaaa` use `dns_zone = var.domain`. Each env manages only its own records: `budget` (prod) and `drill.budget` (drill), plus AAAA when IPv6 is attached.
- **The zone is owned by Scaleway Domains** (it comes with the registration). It is never in Terraform state. `terraform destroy` on drill removes only `drill.budget` A/AAAA. Prod records and the zone are untouched.
- **`managed_dns_zone` keeps its name and now means** "the zone is hosted at Scaleway DNS and already exists; Terraform manages this env's records in it". It never creates the zone. `false` keeps the external-zone path unchanged: `modules/dns` creates nothing and the operator maintains records at the registrar. The variable name is kept so existing gitignored `terraform.tfvars` files stay valid.
- **No import step is needed**, because the zone is not in state at all.

## Consequences

- Zone-level settings (DNSSEC, other records such as MX, TXT) stay manual or are handled by a future dedicated zone state. Out of scope for v1.
- If the domain is ever registered elsewhere and delegated to Scaleway DNS, the zone must be created once by hand in the console (or a separate state) before `managed_dns_zone = true`. The module fails at apply with a Scaleway error if the zone does not exist.
- A same-name record created by hand collides on first apply. Delete it first or import it (`terraform import scaleway_domain_record.a <zone>/<record-id>`).
- ADR-0035's "DNS zone" row is superseded by this ADR. The `dns/` line in its module tree reads "A + AAAA records", which is now accurate.
