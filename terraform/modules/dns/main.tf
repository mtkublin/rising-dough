# DNS wiring for the app host.
# ADR-0035 §3: managed Scaleway zone, or external zone with records-only mode.
#
# When managed_zone = true, Terraform creates the zone itself and the
# A/AAAA records. When false, the operator maintains the zone out-of-band
# (e.g. at their registrar) and this module is a no-op guard so that the
# composition stays clean.

resource "scaleway_domain_zone" "zone" {
  count = var.managed_zone ? 1 : 0

  domain    = var.domain
  subdomain = ""
}

resource "scaleway_domain_record" "a" {
  count = var.managed_zone ? 1 : 0

  dns_zone = var.domain
  name     = var.subdomain
  type     = "A"
  data     = var.instance_ipv4
  ttl      = var.record_ttl_secs

  depends_on = [scaleway_domain_zone.zone]
}

resource "scaleway_domain_record" "aaaa" {
  count = var.managed_zone && var.instance_ipv6 != null ? 1 : 0

  dns_zone = var.domain
  name     = var.subdomain
  type     = "AAAA"
  data     = var.instance_ipv6
  ttl      = var.record_ttl_secs

  depends_on = [scaleway_domain_zone.zone]
}
