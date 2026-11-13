# Scaleway Stardust1-S + Flex IPv4 + security group + cloud-init user_data.
# ADR-0032 §1, ADR-0035 §5.

locals {
  public_web_rules = var.tailnet_only ? [] : [
    { protocol = "TCP", port = 80 },
    { protocol = "TCP", port = 443 },
    { protocol = "UDP", port = 443 },
  ]
}

resource "scaleway_instance_security_group" "app" {
  name                    = "${var.name_prefix}-sg"
  description             = "Inbound HTTP / HTTPS for ${var.name_prefix} (none on a tailnet-only drill, ADR-0101); SSH only over Tailscale (ADR-0094)."
  inbound_default_policy  = "drop"
  outbound_default_policy = "accept"
  stateful                = true
  zone                    = var.scaleway_zone

  # ADR-0094 (T-D67): no inbound TCP 22. SSH is reachable only over the
  # Tailscale tailnet (outbound-only NAT traversal / DERP; no inbound UDP
  # 41641 opened either).

  # ADR-0101: public web ports only when the env is public (prod). A
  # tailnet-only drill has no public inbound web rule at all (tailnet traffic
  # arrives through the outbound-established WireGuard/DERP path).
  dynamic "inbound_rule" {
    for_each = local.public_web_rules
    content {
      action   = "accept"
      protocol = inbound_rule.value.protocol
      port     = inbound_rule.value.port
    }
  }

  # T-D81 / ADR-0094: drill-only break-glass. Empty list (default, always on
  # prod) renders no rule. `ip_range` accepts IPv4 and IPv6 CIDRs.
  dynamic "inbound_rule" {
    for_each = toset(var.break_glass_ssh_cidrs)
    content {
      action   = "accept"
      protocol = "TCP"
      port     = 22
      ip_range = inbound_rule.value
    }
  }
}

resource "scaleway_instance_ip" "ipv4" {
  type = "routed_ipv4"
  zone = var.scaleway_zone
}

resource "scaleway_instance_ip" "ipv6" {
  type = "routed_ipv6"
  zone = var.scaleway_zone
}

resource "scaleway_instance_server" "app" {
  name              = "${var.name_prefix}-vm"
  type              = var.instance_type
  image             = var.image
  zone              = var.scaleway_zone
  security_group_id = scaleway_instance_security_group.app.id
  ip_ids = [
    scaleway_instance_ip.ipv4.id,
    scaleway_instance_ip.ipv6.id,
  ]

  # T-D83 / ADR-0098: the provider schema does not mark cloud_init sensitive,
  # and Terraform printed the PRIOR (state) value in plain text on update or
  # -replace. sensitive() makes the state record it as a sensitive attribute.
  # Note: cloud-init runs once; a user-data change needs
  # -replace=module.compute.scaleway_instance_server.app (an in-place update
  # only rewrites the stored value).
  cloud_init = sensitive(local.user_data)

  tags = concat(
    [
      "budget-planner",
      var.name_prefix,
    ],
    var.expires_at == "" ? [] : ["expires-at=${var.expires_at}"],
  )

  lifecycle {
    create_before_destroy = false
  }
}
