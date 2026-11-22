# ADR-0118: The VM Root Volume Is Local SSD, Declared Explicitly

- **Status**: Accepted (2026-11-21; implemented, was Proposed)
- **Date**: 2026-11-18
- **Amends**: ADR-0032 (shared volume, cost model)
- **Relates to**: ADR-0035, ADR-0084, ADR-0099, ADR-0111, ADR-0114
- **Task**: T-D143

## Context

ADR-0032 assumed `STARDUST1-S` boots from its 10 GB local SSD, which is included in the instance price. `terraform/modules/compute/main.tf` sets no `root_volume` block, so the Scaleway provider picks its current default, a Block Storage (SBS) volume. Prod billing for November 2026 shows a separate "Block Storage Volume" line (€0.35 for about 13.6 days, about €0.78/mo), next to the Flexible IPv4 (€1.31, the expected €0.004/h).

Scaleway's public server catalog (`GET /instance/v1/zones/pl-waw-2/products/servers`, 2026-11-18) lists `STARDUST1-S` with `per_volume_constraint.l_ssd` (min 1 GB) and `volumes_constraint.max_size` 10 GB, so a 10 GB local-SSD root is allowed. `DEV1-S` (the drill type, ADR-0032 amendment T-D123) also lists `l_ssd`.

## Decision

1. `scaleway_instance_server.app` declares `root_volume { volume_type = "l_ssd", size_in_gb = 10 }` for prod and drill. The root type is no longer left to the provider default.
2. A render test pins the root volume type and size, so a provider default change cannot move the host back to SBS silently.
3. The change replaces the VM (root volume type forces a new server). The flexible IPv4/IPv6 resources are separate and stay, so DNS does not change.
4. Rollout: drill gate first (proves the Ubuntu image boots from `l_ssd` and the stack fits in 10 GB with the 1 GiB swapfile), then a normal prod release (ADR-0099). On the new prod VM the compose `litestream restore -if-db-not-exists -if-replica-exists` step restores the database from the replica. Before the apply the operator confirms Litestream is current (ADR-0114) and accepts a short outage.

## Consequences

- Saves about €0.78/mo; prod cost back in line with the ADR-0032 model (instance + Flex IPv4 only).
- Local SSD lives on the hypervisor: it cannot be detached or moved to another VM, and Scaleway can lose it with the host. This matches ADR-0032's stance; Litestream is the durability layer, not the disk.
- The prod release that applies it is a VM replacement: new host keys, new tailnet node, new Caddy certificate (HTTP-01; well under the weekly limit), data from Litestream.
- Rejected: keeping SBS (pays for a property, detachable storage, that ADR-0032 already declined); a smaller root (10 GB is the type's maximum and the ADR-0032 sizing).
