# DNS wiring for the app host.
# ADR-0035 §3 as amended by ADR-0088: this module NEVER creates or owns the
# zone. The root zone of a domain registered at Scaleway Domains already
# exists, and drill + prod are separate states, so a zone resource here would
# be owned twice and a drill destroy could delete prod records.
#
# managed_zone = true  -> zone is hosted at Scaleway DNS; this env's A/AAAA
#                         records are created in it (zone referenced by name).
# managed_zone = false -> zone lives elsewhere (e.g. registrar); no-op, the
#                         operator maintains records out-of-band.

resource "scaleway_domain_record" "a" {
  count = var.managed_zone ? 1 : 0

  dns_zone = var.domain
  name     = var.subdomain
  type     = "A"
  data     = var.instance_ipv4
  ttl      = var.record_ttl_secs
}

resource "scaleway_domain_record" "aaaa" {
  count = var.managed_zone ? 1 : 0 # plan-time known; the address itself is not

  dns_zone = var.domain
  name     = var.subdomain
  type     = "AAAA"
  data     = var.instance_ipv6
  ttl      = var.record_ttl_secs
}
