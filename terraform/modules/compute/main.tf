# Scaleway Stardust1-S + Flex IPv4 + security group + cloud-init user_data.
# ADR-0032 §1, ADR-0035 §5.

resource "scaleway_instance_security_group" "app" {
  name                    = "${var.name_prefix}-sg"
  description             = "Inbound SSH / HTTP / HTTPS for ${var.name_prefix}."
  inbound_default_policy  = "drop"
  outbound_default_policy = "accept"
  stateful                = true
  zone                    = var.scaleway_zone

  inbound_rule {
    action   = "accept"
    protocol = "TCP"
    port     = 22
  }

  inbound_rule {
    action   = "accept"
    protocol = "TCP"
    port     = 80
  }

  inbound_rule {
    action   = "accept"
    protocol = "TCP"
    port     = 443
  }

  inbound_rule {
    action   = "accept"
    protocol = "UDP"
    port     = 443
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

  cloud_init = local.user_data

  tags = [
    "budget-planner",
    var.name_prefix,
  ]

  lifecycle {
    create_before_destroy = false
  }
}
