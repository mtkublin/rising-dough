# T-D42: CAA records for the app hostname. Run:
#   terraform -chdir=terraform/modules/dns init -backend=false
#   terraform -chdir=terraform/modules/dns test

mock_provider "scaleway" {}

variables {
  domain          = "example.eu"
  subdomain       = "budget"
  instance_ipv4   = "192.0.2.10"
  instance_ipv6   = "2001:db8::10"
  zone_project_id = "00000000-0000-0000-0000-000000000000"
}

run "caa_issuers_and_no_wildcard_by_default" {
  command = plan
  variables {
    managed_zone = true
  }

  assert {
    condition = (
      length(scaleway_domain_record.caa_issue) == 2
      && scaleway_domain_record.caa_issue["letsencrypt.org"].data == "0 issue \"letsencrypt.org\""
      && scaleway_domain_record.caa_issue["sectigo.com"].data == "0 issue \"sectigo.com\""
      && scaleway_domain_record.caa_issue["letsencrypt.org"].type == "CAA"
      && scaleway_domain_record.caa_issue["letsencrypt.org"].name == "budget"
    )
    error_message = "CAA must allow exactly Let's Encrypt and Sectigo (ZeroSSL) on the app hostname."
  }

  assert {
    condition     = length(scaleway_domain_record.caa_issuewild) == 1 && scaleway_domain_record.caa_issuewild[0].data == "0 issuewild \";\""
    error_message = "Wildcard issuance must be forbidden."
  }
}

run "no_caa_when_zone_not_managed" {
  command = plan
  variables {
    managed_zone = false
  }

  assert {
    condition     = length(scaleway_domain_record.caa_issue) == 0 && length(scaleway_domain_record.caa_issuewild) == 0
    error_message = "Unmanaged zone: no records at all."
  }
}

run "empty_issuer_list_creates_nothing" {
  command = plan
  variables {
    managed_zone = true
    caa_issuers  = []
  }

  assert {
    condition     = length(scaleway_domain_record.caa_issue) == 0 && length(scaleway_domain_record.caa_issuewild) == 0
    error_message = "An empty issuer list must not create an issuewild-only CAA set."
  }
}
