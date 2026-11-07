# T-D77: offline render of the real user-data path with mocked providers.
# Run: terraform -chdir=terraform init -backend=false && terraform -chdir=terraform test

mock_provider "scaleway" {}
mock_provider "tailscale" {}
mock_provider "random" {}

run "user_data_starts_with_cloud_config" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = startswith(nonsensitive(output.user_data), "#cloud-config\n")
    error_message = "cloud-init ignores user-data unless `#cloud-config` is line 1 (T-D75)."
  }
}

run "user_data_without_restore_helper" {
  command = plan

  module {
    source = "./tests/render"
  }

  variables {
    enable_restore_helper = false
  }

  assert {
    condition     = startswith(nonsensitive(output.user_data), "#cloud-config\n")
    error_message = "cloud-init ignores user-data unless `#cloud-config` is line 1 (T-D75)."
  }
}

run "user_data_has_no_break_glass_rule_by_default" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = length(regexall("ufw allow from", nonsensitive(output.user_data))) == 0
    error_message = "No break-glass ufw rule may render when break_glass_ssh_cidrs is empty (T-D81)."
  }
}

run "user_data_renders_break_glass_ufw_rules_before_enable" {
  command = plan

  module {
    source = "./tests/render"
  }

  variables {
    break_glass_ssh_cidrs = ["203.0.113.7/32", "2001:db8::/64"]
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "ufw allow from 203.0.113.7/32 to any port 22 proto tcp")
    error_message = "IPv4 break-glass CIDR must render a ufw allow rule (T-D81)."
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "ufw allow from 2001:db8::/64 to any port 22 proto tcp")
    error_message = "IPv6 break-glass CIDR must render a ufw allow rule (T-D81)."
  }

  assert {
    condition     = startswith(nonsensitive(output.user_data), "#cloud-config\n")
    error_message = "#cloud-config must stay line 1 (T-D75)."
  }
}

# T-D81: the cross-variable validation lives on the ROOT variable.
run "break_glass_rejected_on_prod" {
  command = plan

  variables {
    env                           = "prod"
    break_glass_ssh_cidrs         = ["203.0.113.7/32"]
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    github_deploy_pubkey          = "ssh-ed25519 AAAA deploy"
    ghcr_pull_pat                 = "ghp_dummy"
    litestream_age_identity       = "AGE-SECRET-KEY-1DUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMY"
    litestream_age_recipient      = "age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
  }

  expect_failures = [var.break_glass_ssh_cidrs]
}

# T-D82: swapfile + swappiness are rendered.
run "user_data_renders_swapfile_and_swappiness" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "filename: /swapfile")
    error_message = "cloud-init must create /swapfile via the swap: key (T-D82)."
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "vm.swappiness")
    error_message = "vm.swappiness must be set (T-D82)."
  }
}
