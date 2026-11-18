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

  dns_zone   = var.domain
  project_id = var.zone_project_id # ADR-0092: the zone lives in the prod project
  name       = var.subdomain
  type       = "A"
  data       = var.instance_ipv4
  ttl        = var.record_ttl_secs
}

# T-D42 / audit F4: restrict which CAs may issue for the app hostname. Caddy
# (no `acme_ca`/`issuer` override in the Caddyfile) uses its default issuers,
# Let's Encrypt first with ZeroSSL as fallback; ZeroSSL issues through Sectigo,
# whose CAA identifier is `sectigo.com`. Both must be listed or a fallback
# issuance would be refused. Scoped to the app hostname (not the zone apex) so
# other names in the zone are unaffected. No wildcards (`issuewild ";"`).
resource "scaleway_domain_record" "caa_issue" {
  for_each = var.managed_zone ? toset(var.caa_issuers) : toset([])

  dns_zone   = var.domain
  project_id = var.zone_project_id # ADR-0092
  name       = var.subdomain
  type       = "CAA"
  data       = "0 issue \"${each.value}\""
  ttl        = var.record_ttl_secs
}

resource "scaleway_domain_record" "caa_issuewild" {
  count = var.managed_zone && length(var.caa_issuers) > 0 ? 1 : 0

  dns_zone   = var.domain
  project_id = var.zone_project_id # ADR-0092
  name       = var.subdomain
  type       = "CAA"
  data       = "0 issuewild \";\""
  ttl        = var.record_ttl_secs
}

resource "scaleway_domain_record" "aaaa" {
  count = var.managed_zone ? 1 : 0 # plan-time known; the address itself is not

  dns_zone   = var.domain
  project_id = var.zone_project_id # ADR-0092
  name       = var.subdomain
  type       = "AAAA"
  data       = var.instance_ipv6
  ttl        = var.record_ttl_secs
}
