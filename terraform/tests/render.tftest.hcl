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

# T-D83 / ADR-0098: the server's cloud_init (rendered secrets) must be marked
# sensitive so plans never print it.
run "server_cloud_init_is_sensitive" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = output.cloud_init_is_sensitive
    error_message = "scaleway_instance_server.app.cloud_init must be sensitive (T-D83, ADR-0098)."
  }

  assert {
    condition     = issensitive(output.user_data)
    error_message = "The compute user_data output must stay sensitive (T-D83)."
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
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    restore_reader_application_id = "00000000-0000-4000-8000-0000000000a3"
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

# T-D84: docker group must exist before `users` runs.
run "user_data_declares_docker_group_before_users" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = length(regexall("(?m)^groups:\\n  - docker\\n", nonsensitive(output.user_data))) == 1
    error_message = "Top-level groups: [docker] must render so useradd -G docker works (T-D84)."
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "ssh_pwauth: false")
    error_message = "SSH password auth must stay disabled (T-D84)."
  }
}

run "user_data_has_no_console_password_by_default" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = !strcontains(nonsensitive(output.user_data), "hashed_passwd")
    error_message = "No hashed_passwd may render by default (T-D84)."
  }

  assert {
    condition     = !strcontains(nonsensitive(output.user_data), "lock_passwd: false")
    error_message = "All users stay lock_passwd: true by default (T-D84)."
  }
}

run "user_data_renders_console_password_hash_for_operator" {
  command = plan

  module {
    source = "./tests/render"
  }

  variables {
    console_password_hash = "$2a$10$dummydummydummydummydummydummydummydummydummydummydummy" # pragma: allowlist secret
  }

  assert {
    condition     = length(regexall("(?m)^    lock_passwd: false\\n    hashed_passwd: '\\$2", nonsensitive(output.user_data))) == 1
    error_message = "operator must get lock_passwd: false + a bcrypt hashed_passwd (T-D84)."
  }

  assert {
    condition     = length(regexall("lock_passwd: false", nonsensitive(output.user_data))) == 1
    error_message = "Only operator may be unlocked (T-D84)."
  }
}

# T-D84: root-level wiring with the (mocked) random provider; also checks the
# hash reaches the compute module and plaintext does not enter user-data.
run "console_password_rejected_on_prod" {
  command = plan

  variables {
    env                           = "prod"
    break_glass_console_password  = true
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
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    restore_reader_application_id = "00000000-0000-4000-8000-0000000000a3"
  }

  expect_failures = [var.break_glass_console_password]
}

# T-D86: drill-only boot log uploader started from bootcmd.
run "boot_log_upload_enabled_renders_uploader" {
  command = plan

  module {
    source = "./tests/render"
  }

  variables {
    boot_log_upload = true
  }

  assert {
    condition     = startswith(nonsensitive(output.user_data), "#cloud-config\n")
    error_message = "#cloud-config must stay line 1 (T-D75)."
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "/run/boot-log-upload.sh")
    error_message = "Enabled: bootcmd must write and start the uploader (T-D86)."
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "https://$BUCKET.s3.$REGION.scw.cloud/boot-logs/")
    error_message = "Enabled: uploader must target the bucket virtual-host URL (T-D86)."
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "'render-check-bucket' 'pl-waw'")
    error_message = "Enabled: the drill bucket name must be rendered into the creds file (T-D86)."
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "tskey-[A-Za-z0-9-]+") && strcontains(nonsensitive(output.user_data), "AGE-SECRET-KEY-1[A-Z0-9]+")
    error_message = "Enabled: uploader must redact tailscale and age keys (T-D86)."
  }
}

run "boot_log_upload_disabled_renders_nothing" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = !strcontains(nonsensitive(output.user_data), "boot-log")
    error_message = "Disabled: no boot-log artefact may be rendered (T-D86)."
  }
}

run "boot_log_upload_rejected_on_prod" {
  command = plan

  variables {
    env                           = "prod"
    boot_log_upload               = true
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
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    restore_reader_application_id = "00000000-0000-4000-8000-0000000000a3"
  }

  expect_failures = [var.boot_log_upload]
}

# T-D90: drill TTL tag. Prod (default) never carries an expires-at tag.
run "server_has_no_expires_at_tag_by_default" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = length([for t in output.server_tags : t if startswith(t, "expires-at=")]) == 0
    error_message = "No expires-at tag may be set when expires_at is empty (T-D90)."
  }
}

run "server_carries_expires_at_tag_when_set" {
  command = plan

  module {
    source = "./tests/render"
  }

  variables {
    expires_at = "2026-11-07T18:30:00Z"
  }

  assert {
    condition     = contains(output.server_tags, "expires-at=2026-11-07T18:30:00Z")
    error_message = "expires_at must be rendered as the expires-at=<RFC3339> server tag (T-D90)."
  }
}

run "drill_expires_at_rejected_on_prod" {
  command = plan

  variables {
    env                           = "prod"
    drill_expires_at              = "2026-11-07T18:30:00Z"
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
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    restore_reader_application_id = "00000000-0000-4000-8000-0000000000a3"
  }

  expect_failures = [var.drill_expires_at]
}

run "drill_expires_at_rejects_malformed" {
  command = plan

  variables {
    env                           = "drill"
    drill_expires_at              = "tomorrow"
    tailnet_dns_name              = "tail0000.ts.net"
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
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  expect_failures = [var.drill_expires_at]
}

# T-D97 / ADR-0101: tailnet-only drill render. Public prod render stays ACME.
run "prod_render_keeps_public_web" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = length(output.security_group_rules) == 3
    error_message = "Prod keeps 80/tcp, 443/tcp and 443/udp public (ADR-0101)."
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "ufw allow 80/tcp") && strcontains(nonsensitive(output.user_data), "email ops@render-check.example.invalid") && strcontains(nonsensitive(output.user_data), "\"80:80\"")
    error_message = "Prod keeps ufw 80, ACME email and the 80:80 port mapping."
  }

  assert {
    condition     = !strcontains(nonsensitive(output.user_data), "/var/run/tailscale")
    error_message = "Prod Caddy must not mount the tailscaled socket."
  }
}

run "drill_render_is_tailnet_only" {
  command = plan

  module {
    source = "./tests/render"
  }

  variables {
    tailnet_only = true
  }

  assert {
    condition     = length(output.security_group_rules) == 0
    error_message = "Tailnet-only drill must have no public web security-group rule (ADR-0101)."
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "budget-planner-drill.tail0000.ts.net {") && strcontains(nonsensitive(output.user_data), "- /var/run/tailscale:/var/run/tailscale")
    error_message = "Drill Caddy serves the ts.net host and mounts the tailscaled socket directory."
  }

  assert {
    condition     = !strcontains(nonsensitive(output.user_data), "ufw allow 80/tcp") && !strcontains(nonsensitive(output.user_data), "\"80:80\"") && !strcontains(nonsensitive(output.user_data), "email ops@") && !strcontains(nonsensitive(output.user_data), "redir https://")
    error_message = "Drill opens no port 80 and has no ACME email or redirect site."
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "ufw allow in on tailscale0 to any port 443")
    error_message = "Drill allows 443 only on tailscale0."
  }
}

run "drill_requires_tailnet_dns_name" {
  command = plan

  variables {
    env                           = "drill"
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
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  expect_failures = [var.tailnet_dns_name]
}

run "tailnet_dns_name_rejected_on_prod" {
  command = plan

  variables {
    env                           = "prod"
    tailnet_dns_name              = "tail0000.ts.net"
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
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    restore_reader_application_id = "00000000-0000-4000-8000-0000000000a3"
  }

  expect_failures = [var.tailnet_dns_name]
}

run "tailnet_dns_name_rejects_malformed" {
  command = plan

  variables {
    env                           = "drill"
    tailnet_dns_name              = "example.com"
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
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  expect_failures = [var.tailnet_dns_name]
}

# T-D103 / ADR-0104: the restore-reader principal is a prod-only input.
run "restore_reader_required_on_prod" {
  command = plan

  variables {
    env                           = "prod"
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
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  expect_failures = [var.restore_reader_application_id]
}

run "restore_reader_rejected_on_drill" {
  command = plan

  variables {
    env                           = "drill"
    tailnet_dns_name              = "tail1234.ts.net"
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
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    restore_reader_application_id = "00000000-0000-4000-8000-0000000000a3"
  }

  expect_failures = [var.restore_reader_application_id]
}
