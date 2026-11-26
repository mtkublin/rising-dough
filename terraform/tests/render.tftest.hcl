# T-D77: offline render of the real user-data path with mocked providers.
# Run: terraform -chdir=terraform init -backend=false && terraform -chdir=terraform test

mock_provider "scaleway" {}
mock_provider "tailscale" {}
mock_provider "random" {}

# T-Q277 / ADR-0135: deterministic stand-in for the generated drill key pair.
mock_provider "age" {
  mock_resource "age_secret_key" {
    defaults = {
      secret_key = "AGE-SECRET-KEY-1MOCKDRILLMOCKDRILLMOCKDRILLMOCKDRILLMOCKDRILLMOCKDRILL" # pragma: allowlist secret
      public_key = "age1mockdrillmockdrillmockdrillmockdrillmockdrillmockdrillmockdr"
    }
  }
}

override_resource {
  target          = random_password.admin_initial_password
  override_during = plan
  values          = { result = "dummyadminpassword0000", bcrypt_hash = "x" }
}

override_resource {
  target          = random_password.cookie_secret
  override_during = plan
  values          = { result = "dummycookiesecret0000000000000000000000000000000000" }
}

override_resource {
  target          = tailscale_tailnet_key.vm
  override_during = plan
  values          = { key = "tskey-auth-DUMMY" } # pragma: allowlist secret
}

# Known at plan time so assertions can read the rendered host config.
override_resource {
  target          = age_secret_key.drill
  override_during = plan
  values = {
    secret_key = "AGE-SECRET-KEY-1MOCKDRILLMOCKDRILLMOCKDRILLMOCKDRILLMOCKDRILLMOCKDRILL" # pragma: allowlist secret
    public_key = "age1mockdrillmockdrillmockdrillmockdrillmockdrillmockdrillmockdr"
  }
}

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

# T-UR22 / ADR-0134 section 9: a drill has no bootstrap admin by default and
# gets the per-deploy setup token hash; prod keeps the bootstrap admin.
run "compose_without_admin_email_has_no_bootstrap_admin" {
  command = plan

  module {
    source = "./tests/render"
  }

  variables {
    admin_email      = ""
    setup_token_hash = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" # pragma: allowlist secret
  }

  assert {
    condition     = !strcontains(one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/docker-compose.yml")]), "BUDGET_PLANNER_ADMIN_EMAIL")
    error_message = "Empty admin_email must render no bootstrap admin email (T-UR22)."
  }

  assert {
    condition     = !strcontains(one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/docker-compose.yml")]), "BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD")
    error_message = "Empty admin_email must render no initial admin password (T-UR22)."
  }

  assert {
    condition     = strcontains(one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/docker-compose.yml")]), "BUDGET_PLANNER_SETUP_TOKEN_HASH: \"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\"")
    error_message = "The drill setup token hash must reach the compose env (T-UR22)."
  }
}

run "compose_with_admin_email_keeps_bootstrap_admin" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = strcontains(one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/docker-compose.yml")]), "BUDGET_PLANNER_ADMIN_EMAIL: \"admin@example.invalid\"")
    error_message = "A set admin_email keeps the bootstrap admin (prod unchanged)."
  }

  assert {
    condition     = !strcontains(one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/docker-compose.yml")]), "BUDGET_PLANNER_SETUP_TOKEN_HASH")
    error_message = "No hash, no setup token env."
  }
}

# T-UR22: empty admin_email is allowed for a drill only.
run "empty_admin_email_rejected_on_prod" {
  command = plan

  variables {
    env                           = "prod"
    admin_email                   = ""
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
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

  expect_failures = [var.admin_email]
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

# T-D83 / ADR-0098 / ADR-0111: the server's user_data (rendered secrets) must
# be marked sensitive so plans never print it.
run "server_user_data_is_sensitive" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = output.user_data_is_sensitive
    error_message = "scaleway_instance_server.app.user_data must be sensitive (T-D83, ADR-0098, ADR-0111)."
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
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
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
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
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
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
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
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
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
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  expect_failures = [var.drill_expires_at]
}

# T-Q309 / ADR-0132: the prod PR plan runs with placeholder Tailscale credentials
# (no OAuth client in prod-plan); the render is identical to one with real ones.
run "prod_plan_only_placeholder_tailscale_credentials" {
  command = plan

  module {
    source = "./tests/render"
  }

  variables {
    env                           = "prod"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "placeholder"
    litestream_age_identity       = "AGE-SECRET-KEY-1DUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMY"
    litestream_age_recipient      = "age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq"
    tailscale_oauth_client_id     = "plan-only-no-credential"
    tailscale_oauth_client_secret = "plan-only-no-credential" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    restore_reader_application_id = "00000000-0000-4000-8000-0000000000a3"
  }

  assert {
    condition     = strcontains(nonsensitive(output.all_rendered), "ufw allow 80/tcp")
    error_message = "Prod renders identically with placeholder Tailscale credentials (T-Q309)."
  }
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
    condition     = strcontains(nonsensitive(output.all_rendered), "ufw allow 80/tcp") && strcontains(nonsensitive(output.all_rendered), "email ops@render-check.example.invalid")
    error_message = "Prod keeps ufw 80 and the ACME email (Caddy is host-networked since ADR-0133, so there is no 80:80 mapping)."
  }

  assert {
    condition     = !strcontains(nonsensitive(output.all_rendered), "/var/run/tailscale")
    error_message = "Prod Caddy must not mount the tailscaled socket."
  }
}

# T-Q306(c) / ADR-0149: seed-demo is a drill-only host file, independent of the restore helper.
run "seed_demo_installed_on_drill" {
  command = plan

  module {
    source = "./tests/render"
  }

  variables {
    enable_seed_helper    = true
    enable_restore_helper = false
  }

  assert {
    condition     = contains([for f in jsondecode(nonsensitive(output.host_config)).files : f.path], "/usr/local/bin/seed-demo")
    error_message = "seed-demo must be an agent-managed file on the drill (T-Q306(c))."
  }

  assert {
    condition     = !contains([for f in jsondecode(nonsensitive(output.host_config)).files : f.path], "/usr/local/bin/restore-from-prod") && !strcontains(nonsensitive(output.all_rendered), "RESTORE_ACCESS_KEY_ID=")
    error_message = "seed-demo must work without the restore helper or any prod credential."
  }
}

run "seed_demo_absent_on_prod" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = !contains([for f in jsondecode(nonsensitive(output.host_config)).files : f.path], "/usr/local/bin/seed-demo")
    error_message = "seed-demo must never be installed outside the drill (T-Q306(c))."
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
    condition     = strcontains(nonsensitive(output.all_rendered), "budget-planner-drill.tail0000.ts.net {") && strcontains(nonsensitive(output.all_rendered), "- /var/run/tailscale:/var/run/tailscale")
    error_message = "Drill Caddy serves the ts.net host and mounts the tailscaled socket directory."
  }

  assert {
    condition     = !strcontains(nonsensitive(output.all_rendered), "ufw allow 80/tcp") && !strcontains(nonsensitive(output.all_rendered), "\"80:80\"") && !strcontains(nonsensitive(output.all_rendered), "email ops@") && !strcontains(nonsensitive(output.all_rendered), "redir https://")
    error_message = "Drill opens no port 80 and has no ACME email or redirect site."
  }

  assert {
    condition     = strcontains(nonsensitive(output.all_rendered), "ufw allow in on tailscale0 to any port 443")
    error_message = "Drill allows 443 only on tailscale0."
  }

  # T-Q255 (Q-078, ADR-0101 amendment): Caddy is host-networked, so Docker publishes
  # nothing for it (DOCKER-USER does not see that traffic) and the host INPUT filter
  # (ufw, tailscale0 only) is the control. The only published port is the app's
  # loopback bind.
  assert {
    condition     = strcontains(nonsensitive(output.all_rendered), "\"127.0.0.1:8000:8000\"") && !strcontains(nonsensitive(output.all_rendered), "\"0.0.0.0:") && length(regexall("- \"[0-9]+:[0-9]+\"", nonsensitive(output.all_rendered))) == 0
    error_message = "Drill must publish no container port beyond the loopback app bind (T-Q255)."
  }
}

run "images_and_packages_are_pinned" {
  command = plan

  module {
    source = "./tests/render"
  }

  # T-Q255 (Q-067): Caddy and Litestream by digest, tailscale by exact apt version.
  assert {
    condition     = strcontains(nonsensitive(output.all_rendered), "image: caddy:2.8@sha256:") && !strcontains(nonsensitive(output.all_rendered), "image: caddy:2.8\n")
    error_message = "Caddy image must be pinned by @sha256 digest."
  }

  assert {
    condition     = strcontains(nonsensitive(output.all_rendered), "image: litestream/litestream:0.3.14@sha256:") && !strcontains(nonsensitive(output.all_rendered), "image: litestream/litestream:0.3.14\n")
    error_message = "Litestream image must be pinned by @sha256 digest."
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "apt-get install -y tailscale=")
    error_message = "tailscale must be installed at an exact pinned version."
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
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
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
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
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
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
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
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
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
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    restore_reader_application_id = "00000000-0000-4000-8000-0000000000a3"
  }

  expect_failures = [var.restore_reader_application_id]
}

# T-D123: Scaleway allows one STARDUST1-S per organisation (prod's). The drill
# runs on a different type so it can coexist with prod; prod stays pinned.
run "prod_instance_type_is_stardust" {
  command = plan

  variables {
    env                           = "prod"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
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

  assert {
    condition     = module.compute.server_type == "STARDUST1-S"
    error_message = "prod must stay on STARDUST1-S (ADR-0032)."
  }

  assert {
    condition     = module.compute.root_volume_type == "l_ssd" && module.compute.root_volume_size_gb == 10
    error_message = "prod must boot from a 10 GB local SSD, not Block Storage (T-D143, ADR-0118)."
  }

  assert {
    condition     = module.compute.allow_empty_db == false
    error_message = "prod must refuse to start an empty database by default (T-D156, ADR-0127)."
  }

  assert {
    condition     = endswith(tailscale_tailnet_key.vm.description, " vm ${output.vm_spec_id}")
    error_message = "the Tailscale key description must carry the VM spec hash so a new VM gets a new key (T-D156, ADR-0127)."
  }
}

run "drill_instance_type_defaults_to_dev1_s" {
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
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  assert {
    condition     = module.compute.server_type == "DEV1-S"
    error_message = "drill must default to DEV1-S (T-D123: STARDUST1-S quota is 1 per org)."
  }

  assert {
    condition     = module.compute.root_volume_type == "l_ssd" && module.compute.root_volume_size_gb == 10
    error_message = "drill must boot from a 10 GB local SSD, not Block Storage (T-D143, ADR-0118)."
  }

  assert {
    condition     = module.compute.allow_empty_db == true
    error_message = "the drill bucket starts empty, so the drill must allow an empty database (T-D156, ADR-0127)."
  }
}

# T-D156 / ADR-0127: a different VM spec means a different key description,
# which forces a new single-use Tailscale key in the plan that replaces the VM.
run "vm_spec_change_replaces_tailscale_key" {
  command = plan

  variables {
    env                           = "drill"
    drill_instance_type           = "DEV1-M"
    tailnet_dns_name              = "tail1234.ts.net"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  assert {
    condition     = output.vm_spec_id != run.drill_instance_type_defaults_to_dev1_s.vm_spec_id
    error_message = "a changed instance type must change vm_spec_id (T-D156, ADR-0127)."
  }
}

run "prod_allow_empty_db_is_explicit" {
  command = plan

  variables {
    env                           = "prod"
    allow_empty_db                = true
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
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

  assert {
    condition     = module.compute.allow_empty_db == true
    error_message = "allow_empty_db = true must reach the restore service (T-D156, ADR-0127)."
  }
}

# ADR-0127 §7: the replacement rehearsal's drill-only knobs; prod ignores both.
run "drill_rehearsal_knobs_reach_the_vm" {
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
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    drill_root_volume_type        = "sbs_volume"
    drill_allow_empty_db          = false
  }

  assert {
    condition     = module.compute.root_volume_type == "sbs_volume"
    error_message = "drill_root_volume_type must reach the drill VM (ADR-0127 §7)."
  }

  assert {
    condition     = module.compute.allow_empty_db == false
    error_message = "drill_allow_empty_db = false must reach the restore service (ADR-0127 §7)."
  }

  assert {
    condition     = output.vm_spec_id != run.drill_instance_type_defaults_to_dev1_s.vm_spec_id
    error_message = "the Block Storage -> l_ssd move must change vm_spec_id, as T-D143 does on prod."
  }
}

run "prod_ignores_drill_rehearsal_knobs" {
  command = plan

  variables {
    env                           = "prod"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    litestream_age_identity       = "AGE-SECRET-KEY-1DUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMY"
    litestream_age_recipient      = "age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    restore_reader_application_id = "00000000-0000-4000-8000-0000000000a3"
    drill_root_volume_type        = "sbs_volume"
    drill_allow_empty_db          = true
  }

  assert {
    condition     = module.compute.root_volume_type == "l_ssd"
    error_message = "prod must stay on l_ssd whatever drill_root_volume_type says (ADR-0127 §7)."
  }

  assert {
    condition     = module.compute.allow_empty_db == false
    error_message = "prod must ignore drill_allow_empty_db (ADR-0127 §7)."
  }
}

run "drill_root_volume_type_rejects_other_types" {
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
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    drill_root_volume_type        = "b_ssd"
  }

  expect_failures = [var.drill_root_volume_type]
}

# T-Q238: drills verify branch builds under the drill identity; no ancestry check.
run "drill_cosign_identity_accepts_branch_builds" {
  command = plan

  module {
    source = "./tests/render"
  }

  variables {
    allow_branch_builds = true
  }

  assert {
    condition     = jsondecode(nonsensitive(output.host_config)).cosign.identity_regexp == "^https://github\\.com/render-check-owner/render-check-repo/\\.github/workflows/build\\.yml@refs/(heads|tags)/.+$"
    error_message = "drill cosign identity must accept branch builds of build.yml (T-Q238)."
  }

  assert {
    condition     = jsondecode(nonsensitive(output.host_config)).ancestry.enabled == false
    error_message = "drill must not require main ancestry (T-Q238)."
  }
}

# ADR-0111: bp-config carries the digest-pinned image, the cosign policy and
# the managed files; cloud-init is only the fixed bootstrap.
run "host_config_pins_image_and_policy" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = jsondecode(nonsensitive(output.host_config)).image.ref == "ghcr.io/render-check-owner/budget-planner:sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    error_message = "bp-config image.ref must be repo:tag@digest (ADR-0111)."
  }

  # T-Q238 (Q-040): prod accepts only build.yml signed from main or a release tag.
  assert {
    condition     = jsondecode(nonsensitive(output.host_config)).cosign.identity_regexp == "^https://github\\.com/render-check-owner/render-check-repo/\\.github/workflows/build\\.yml@(refs/heads/main|refs/tags/v[0-9][0-9A-Za-z.+-]*)$"
    error_message = "prod cosign identity must be build.yml@main or a v* tag (T-Q238)."
  }

  assert {
    condition     = jsondecode(nonsensitive(output.host_config)).ancestry == { enabled = true, repo = "render-check-owner/render-check-repo", branch = "main" }
    error_message = "prod must require sha-* images to be ancestors of main (T-Q238)."
  }

  assert {
    condition     = jsondecode(nonsensitive(output.host_config)).generation == output.host_config_generation
    error_message = "bp-config generation must match the output the CI monitor waits for."
  }

  assert {
    condition = strcontains(
      one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/docker-compose.yml")]),
      "image: ghcr.io/render-check-owner/budget-planner:sha-1234567@sha256:0123456789abcdef"
    )
    error_message = "The managed compose file must run the digest-pinned image."
  }

  assert {
    condition = strcontains(
      one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/docker-compose.yml")]),
      "BUDGET_WEBAUTHN_RP_ID: \"render-check.example.invalid\"\n      BUDGET_WEBAUTHN_ORIGIN: \"https://render-check.example.invalid\""
    )
    error_message = "Compose must render the WebAuthn RP id and origin from the public hostname (T-D135, ADR-0067 §1)."
  }

  assert {
    condition = strcontains(
      one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/docker-compose.yml")]),
      "BUDGET_FX_REFRESH_ENABLED: \"true\""
    )
    error_message = "Compose must enable the daily FX refresh in production (T-Q307, ADR-0146)."
  }

  assert {
    condition = strcontains(
      one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/Caddyfile")]),
      "handle /.well-known/bp-deploy-status.json"
    )
    error_message = "Caddy must serve the agent status for the CI monitor."
  }

  # T-D132: the CSP is set from a response matcher inside reverse_proxy.
  assert {
    condition = strcontains(
      one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/Caddyfile")]),
      "handle_response @html {"
    )
    error_message = "Caddy must set the CSP via a handle_response response matcher (T-D132)."
  }

  # T-Q254 / ADR-0036 addendum: the app owns the nonce CSP (script-src/style-src per ADR-0113);
  # Caddy is a second layer with non-fetch directives only (two CSPs intersect).
  assert {
    condition = (
      strcontains(
        one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/Caddyfile")]),
        "header Content-Security-Policy \"frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'\""
      )
      && !strcontains(
        one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/Caddyfile")]),
        "script-src"
      )
      && !strcontains(
        one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/Caddyfile")]),
        "{vars.nonce}"
      )
    )
    error_message = "Caddy CSP must be the non-fetch second layer with no script-src and no Caddy nonce (T-Q254)."
  }

  assert {
    condition = alltrue([
      for p in ["/etc/budget-planner/litestream-age.key", "/etc/budget-planner/litestream.env", "/root/.docker/config.json", "/usr/local/bin/restore-from-prod"] :
      contains([for f in jsondecode(nonsensitive(output.host_config)).files : f.path], p)
    ])
    error_message = "Secrets files and the drill restore helper must be agent-managed files."
  }

  # T-D136 / ADR-0114: replicate config carries the identity, the entrypoint is
  # agent-managed, and a change to either restarts litestream.
  assert {
    condition = alltrue([
      for needle in ["recipients:", "identities:", "- $${LITESTREAM_AGE_IDENTITY}"] :
      strcontains(one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/litestream.yml")]), replace(needle, "$$", "$"))
    ])
    error_message = "Rendered litestream.yml must carry age recipients and the identity (T-D136)."
  }

  assert {
    condition = alltrue([
      strcontains(one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/docker-compose.yml")]), "entrypoint: [\"/bin/sh\", \"/etc/litestream-entrypoint.sh\"]"),
      strcontains(one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/docker-compose.yml")]), "/etc/budget-planner/litestream-age.key:/run/litestream-age.key:ro"),
      strcontains(one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/litestream-entrypoint.sh")]), "rm -rf \"$META_DIR\""),
    ])
    error_message = "Compose must run the litestream entrypoint with the identity mounted (T-D136)."
  }

  assert {
    condition = alltrue([
      for f in jsondecode(nonsensitive(output.host_config)).files :
      contains(f.restart, "litestream") if endswith(f.path, "/litestream-entrypoint.sh") || endswith(f.path, "/litestream.yml") || endswith(f.path, "/litestream-age.key")
    ])
    error_message = "Changes to the litestream config, entrypoint or identity must restart litestream (T-D136)."
  }
}

run "cloud_init_is_fixed_bootstrap_only" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = !strcontains(nonsensitive(output.user_data), "name: deploy") && !strcontains(nonsensitive(output.user_data), "deploy-budget-planner")
    error_message = "No deploy user or forced-command script (ADR-0111 removes the SSH deploy path)."
  }

  assert {
    condition     = !strcontains(nonsensitive(output.user_data), "/etc/budget-planner/")
    error_message = "App files come from bp-config, not cloud-init (ADR-0111)."
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "--local-port 1-1023 -o \"$dir/bp_agent.py.new\" http://169.254.42.42/user_data/bp-agent")
    error_message = "The loader must fetch bp-agent from metadata over a privileged port."
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "iptables -I DOCKER-USER -d 169.254.42.42/32 -j DROP")
    error_message = "Containers must be blocked from the metadata API (ADR-0111 §6)."
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "systemctl enable --now bp-converge.timer")
    error_message = "The agent timer must be enabled at first boot."
  }
}

run "image_ref_must_be_digest_pinned" {
  command = plan

  variables {
    env                           = "drill"
    app_image_ref                 = "sha-1234567"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    tailnet_dns_name              = "tail0000.ts.net"
  }

  expect_failures = [var.app_image_ref]
}

# T-D135: the drill is tailnet-only, so its WebAuthn RP is the tailnet name.
run "drill_compose_sets_webauthn_rp_to_tailnet_name" {
  command = plan

  module {
    source = "./tests/render"
  }

  variables {
    tailnet_only = true
  }

  assert {
    condition = strcontains(
      one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/docker-compose.yml")]),
      "BUDGET_WEBAUTHN_RP_ID: \"budget-planner-drill.tail0000.ts.net\"\n      BUDGET_WEBAUTHN_ORIGIN: \"https://budget-planner-drill.tail0000.ts.net\""
    )
    error_message = "Drill compose must render the WebAuthn RP from the tailnet hostname (T-D135)."
  }
}

# T-D137: the CI key is authorised on drill hosts only (ADR-0094, ADR-0111).
run "ci_ssh_key_not_rendered_by_default" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = !strcontains(nonsensitive(output.user_data), "ci-deploy")
    error_message = "No CI key may render when ci_ssh_pub is empty (T-D137)."
  }
}

run "ci_ssh_key_renders_as_second_operator_key" {
  command = plan

  module {
    source = "./tests/render"
  }

  variables {
    ci_ssh_pub = "ssh-ed25519 AAAACIKEY ci-deploy"
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "      - 'ssh-ed25519 AAAACIKEY ci-deploy'\n")
    error_message = "A set CI key must be a second ssh_authorized_keys entry (T-D137)."
  }

  assert {
    condition     = strcontains(nonsensitive(output.user_data), "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAADUMMY")
    error_message = "The operator's own key must stay authorised (T-D137)."
  }
}

run "ci_ssh_key_dropped_on_prod_even_when_set" {
  command = plan

  variables {
    env                           = "prod"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    ci_ssh_pubkey                 = "ssh-ed25519 AAAACIKEY ci-deploy"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
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

  assert {
    condition     = output.ci_ssh_authorized == false
    error_message = "Prod must never authorise the CI key, whatever ci_ssh_pubkey holds (T-D137)."
  }
}

run "ci_ssh_key_authorised_on_drill" {
  command = plan

  variables {
    env                           = "drill"
    tailnet_dns_name              = "tail0000.ts.net"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    ci_ssh_pubkey                 = "ssh-ed25519 AAAACIKEY ci-deploy"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  assert {
    condition     = output.ci_ssh_authorized == true
    error_message = "Drill must authorise the CI key when ci_ssh_pubkey is set (T-D137)."
  }
}

run "ci_ssh_key_must_be_a_public_key" {
  command = plan

  variables {
    env                           = "drill"
    tailnet_dns_name              = "tail0000.ts.net"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    ci_ssh_pubkey                 = "not-a-public-key"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  expect_failures = [var.ci_ssh_pubkey]
}

# T-D139 / ADR-0116: the drill's tailnet name (= TLS certificate name) is unique per
# run, because Let's Encrypt allows 5 certificates per exact name per week.
run "drill_run_id_makes_tailnet_name_unique" {
  command = plan

  variables {
    env                           = "drill"
    tailnet_dns_name              = "tail1234.ts.net"
    drill_run_id                  = "44308968526"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  assert {
    condition     = output.tailscale_hostname == "budget-planner-drill-44308968526"
    error_message = "A drill run id must give the VM a per-run tailnet name (ADR-0116)."
  }

  assert {
    condition     = output.fqdn == "budget-planner-drill-44308968526.tail1234.ts.net"
    error_message = "The served hostname (Caddy, WebAuthn RP) must follow the per-run name."
  }
}

run "drill_without_run_id_keeps_fixed_name" {
  command = plan

  variables {
    env                           = "drill"
    tailnet_dns_name              = "tail1234.ts.net"
    drill_run_id                  = ""
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  assert {
    condition     = output.tailscale_hostname == "budget-planner-drill"
    error_message = "Without a run id the drill keeps the fixed tailnet name."
  }
}

run "drill_run_id_rejects_non_digits" {
  command = plan

  variables {
    env                           = "drill"
    tailnet_dns_name              = "tail1234.ts.net"
    drill_run_id                  = "abc"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  expect_failures = [var.drill_run_id]
}

run "drill_run_id_rejected_on_prod" {
  command = plan

  variables {
    env                           = "prod"
    drill_run_id                  = "123"
    restore_reader_application_id = "00000000-0000-4000-8000-0000000000a3"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    litestream_age_identity       = "AGE-SECRET-KEY-1DUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMYDUMMY"
    litestream_age_recipient      = "age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  expect_failures = [var.drill_run_id]
}

# T-D156 / ADR-0127: the restore service runs the guard script, which the agent
# writes, and gets the empty-DB flag.
run "restore_guard_rendered_and_closed_by_default" {
  command = plan

  module {
    source = "./tests/render"
  }

  assert {
    condition     = strcontains(one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/docker-compose.yml")]), "LITESTREAM_ALLOW_EMPTY_DB: \"false\"")
    error_message = "the restore service must refuse an empty database by default (T-D156, ADR-0127)."
  }

  assert {
    condition     = length([for f in jsondecode(nonsensitive(output.host_config)).files : f if endswith(f.path, "/litestream-restore.sh") && f.mode == "0755"]) == 1
    error_message = "the host agent must write litestream-restore.sh at 0755 (T-D156, ADR-0127)."
  }
}

run "restore_guard_flag_renders_true" {
  command = plan

  module {
    source = "./tests/render"
  }

  variables {
    allow_empty_db = true
  }

  assert {
    condition     = strcontains(one([for f in jsondecode(nonsensitive(output.host_config)).files : f.content if endswith(f.path, "/docker-compose.yml")]), "LITESTREAM_ALLOW_EMPTY_DB: \"true\"")
    error_message = "allow_empty_db = true must reach the restore service (T-D156, ADR-0127)."
  }
}

# ----------------------------------------------------------------------------
# T-Q277 / ADR-0135: per-drill age key pair generated in Terraform.
# ----------------------------------------------------------------------------

run "drill_generates_age_key_pair_and_needs_no_age_input" {
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
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  assert {
    condition     = length(age_secret_key.drill) == 1
    error_message = "A drill must generate its own age key pair (ADR-0135)."
  }

  assert {
    condition     = strcontains(one([for f in jsondecode(nonsensitive(module.compute.host_config)).files : f.content if endswith(f.path, "/litestream-age.key")]), "AGE-SECRET-KEY-1MOCKDRILL")
    error_message = "The drill host's own identity file must carry the generated secret key."
  }

  assert {
    condition     = strcontains(one([for f in jsondecode(nonsensitive(module.compute.host_config)).files : f.content if endswith(f.path, "/litestream.yml")]), "age1mockdrill")
    error_message = "The drill replica must be encrypted to the generated public key."
  }

  assert {
    condition     = length([for f in jsondecode(nonsensitive(module.compute.host_config)).files : f.path if endswith(f.path, "/restore-source-age.key")]) == 0
    error_message = "Without the restore helper no restore-source identity may reach the host."
  }
}

run "drill_rejects_supplied_age_identity" {
  command = plan

  variables {
    env                           = "drill"
    tailnet_dns_name              = "tail1234.ts.net"
    litestream_age_identity       = "AGE-SECRET-KEY-1PRODPRODPRODPRODPRODPRODPRODPRODPRODPRODPRODPRODPROD"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  expect_failures = [var.litestream_age_identity]
}

run "drill_rejects_supplied_age_recipient" {
  command = plan

  variables {
    env                           = "drill"
    tailnet_dns_name              = "tail1234.ts.net"
    litestream_age_recipient      = "age1prodprodprodprodprodprodprodprodprodprodprodprodprodprodpr"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  expect_failures = [var.litestream_age_recipient]
}

run "prod_requires_age_identity" {
  command = plan

  variables {
    env                           = "prod"
    litestream_age_recipient      = "age1prodprodprodprodprodprodprodprodprodprodprodprodprodprodpr"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    restore_reader_application_id = "00000000-0000-4000-8000-0000000000a3"
  }

  expect_failures = [var.litestream_age_identity]
}

run "prod_requires_age_recipient" {
  command = plan

  variables {
    env                           = "prod"
    litestream_age_identity       = "AGE-SECRET-KEY-1PRODPRODPRODPRODPRODPRODPRODPRODPRODPRODPRODPRODPROD"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    restore_reader_application_id = "00000000-0000-4000-8000-0000000000a3"
  }

  expect_failures = [var.litestream_age_recipient]
}

run "prod_rejects_malformed_age_identity" {
  command = plan

  variables {
    env                           = "prod"
    litestream_age_identity       = "not-an-age-key"
    litestream_age_recipient      = "age1prodprodprodprodprodprodprodprodprodprodprodprodprodprodpr"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    restore_reader_application_id = "00000000-0000-4000-8000-0000000000a3"
  }

  expect_failures = [var.litestream_age_identity]
}

run "prod_uses_supplied_age_pair_and_generates_none" {
  command = plan

  variables {
    env                           = "prod"
    litestream_age_identity       = "AGE-SECRET-KEY-1PRODPRODPRODPRODPRODPRODPRODPRODPRODPRODPRODPRODPROD"
    litestream_age_recipient      = "age1prodprodprodprodprodprodprodprodprodprodprodprodprodprodpr"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    restore_reader_application_id = "00000000-0000-4000-8000-0000000000a3"
  }

  assert {
    condition     = length(age_secret_key.drill) == 0
    error_message = "Prod must not generate an age key pair (ADR-0135)."
  }

  assert {
    condition     = strcontains(one([for f in jsondecode(nonsensitive(module.compute.host_config)).files : f.content if endswith(f.path, "/litestream-age.key")]), "AGE-SECRET-KEY-1PRODPROD") && strcontains(one([for f in jsondecode(nonsensitive(module.compute.host_config)).files : f.content if endswith(f.path, "/litestream.yml")]), "age1prodprod")
    error_message = "Prod keeps the operator-supplied age pair."
  }
}

run "restore_source_identity_reaches_host_only_with_restore_helper" {
  command = plan

  variables {
    env                           = "drill"
    tailnet_dns_name              = "tail1234.ts.net"
    scw_access_key_restore        = "SCWDUMMYRESTOREKEY000"
    scw_secret_key_restore        = "11111111-dummy-0000-0000-000000000000" # pragma: allowlist secret
    restore_source_age_identity   = "AGE-SECRET-KEY-1RESTORERESTORERESTORERESTORERESTORERESTORERESTORERESTORE"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  assert {
    condition     = strcontains(one([for f in jsondecode(nonsensitive(module.compute.host_config)).files : f.content if endswith(f.path, "/restore-source-age.key")]), "AGE-SECRET-KEY-1RESTORERESTORE")
    error_message = "With the restore helper the prod replica identity must be delivered as restore-source-age.key."
  }

  assert {
    condition     = !strcontains(one([for f in jsondecode(nonsensitive(module.compute.host_config)).files : f.content if endswith(f.path, "/litestream-age.key")]), "RESTORERESTORE") && strcontains(one([for f in jsondecode(nonsensitive(module.compute.host_config)).files : f.content if endswith(f.path, "/litestream-age.key")]), "MOCKDRILL")
    error_message = "The host's own replica identity must stay the drill pair, never the prod identity."
  }
}

run "restore_source_identity_not_rendered_without_restore_helper" {
  command = plan

  variables {
    env                           = "drill"
    tailnet_dns_name              = "tail1234.ts.net"
    restore_source_age_identity   = "AGE-SECRET-KEY-1RESTORERESTORERESTORERESTORERESTORERESTORERESTORERESTORE"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
  }

  assert {
    condition     = length([for f in jsondecode(nonsensitive(module.compute.host_config)).files : f.path if endswith(f.path, "/restore-source-age.key")]) == 0 && !strcontains(nonsensitive(module.compute.host_config), "RESTORERESTORE")
    error_message = "Without scw_access_key_restore (no helper) the prod identity must not reach the host."
  }
}

run "restore_source_identity_rejected_on_prod" {
  command = plan

  variables {
    env                           = "prod"
    litestream_age_identity       = "AGE-SECRET-KEY-1PRODPRODPRODPRODPRODPRODPRODPRODPRODPRODPRODPRODPROD"
    litestream_age_recipient      = "age1prodprodprodprodprodprodprodprodprodprodprodprodprodprodpr"
    restore_source_age_identity   = "AGE-SECRET-KEY-1RESTORERESTORERESTORERESTORERESTORERESTORERESTORERESTORE"
    admin_email                   = "admin@example.invalid"
    scaleway_project_id           = "00000000-0000-4000-8000-000000000000"
    scaleway_organization_id      = "00000000-0000-4000-8000-000000000000"
    domain                        = "example.invalid"
    github_owner                  = "owner"
    operator_ssh_pubkey           = "ssh-ed25519 AAAA operator"
    app_image_ref                 = "sha-1234567@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ghcr_pull_pat                 = "ghp_dummy"
    tailscale_oauth_client_id     = "dummy"
    tailscale_oauth_client_secret = "dummy" # pragma: allowlist secret
    app_application_id            = "00000000-0000-4000-8000-0000000000a1"
    app_scw_access_key            = "SCWDUMMYDUMMYDUMMYDU"
    app_scw_secret_key            = "00000000-0000-4000-8000-0000000000a2" # pragma: allowlist secret
    restore_reader_application_id = "00000000-0000-4000-8000-0000000000a3"
  }

  expect_failures = [var.restore_source_age_identity]
}
