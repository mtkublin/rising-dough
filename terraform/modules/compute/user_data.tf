# ----------------------------------------------------------------------------
# Cloud-init user_data assembly.
# Each template is rendered independently and then composed into the top-level
# bootstrap.yaml.tpl via the `*_rendered` inputs. This keeps indentation safe
# and allows `yq -e .` / `caddy validate --config -` to lint each file in CI.
# ----------------------------------------------------------------------------

locals {
  docker_compose_rendered = templatefile("${path.module}/../../cloud-init/compose/docker-compose.yml.tpl", {
    github_owner           = var.github_owner
    app_image_tag          = var.app_image_tag
    cookie_secret          = var.cookie_secret
    trusted_hosts          = var.trusted_hosts_csv
    admin_email            = var.admin_email
    admin_initial_password = var.admin_password
    scw_access_key         = var.scw_access_key
    scw_secret_key         = var.scw_secret_key
  })

  caddyfile_rendered = templatefile("${path.module}/../../cloud-init/compose/Caddyfile.tpl", {
    hostname = var.hostname
  })

  litestream_rendered = templatefile("${path.module}/../../cloud-init/compose/litestream.yml.tpl", {
    bucket_name     = var.bucket_name
    bucket_endpoint = var.bucket_endpoint
    bucket_region   = var.bucket_region
    age_recipient   = var.litestream_age_recipient
  })

  # T-D56: restore-only config (age identity via $LITESTREAM_AGE_IDENTITY).
  litestream_restore_rendered = templatefile("${path.module}/../../cloud-init/compose/litestream-restore.yml.tpl", {
    bucket_name     = var.bucket_name
    bucket_endpoint = var.bucket_endpoint
    bucket_region   = var.bucket_region
  })

  deploy_script_rendered = templatefile("${path.module}/../../cloud-init/bin/deploy-budget-planner.tpl", {
    owner             = var.github_owner
    app_image         = "ghcr.io/${var.github_owner}/budget-planner"
    compose_dir       = "/etc/budget-planner"
    previous_tag_file = "/etc/budget-planner/previous-tag"
  })

  # T-D41a: drill-only restore helper. Empty string on other environments, which
  # also drops the write_files entries in bootstrap.yaml.tpl.
  restore_script_rendered = var.enable_restore_helper ? templatefile("${path.module}/../../cloud-init/bin/restore-from-prod.tpl", {
    compose_dir      = "/etc/budget-planner"
    restore_env_file = "/etc/budget-planner/restore-source.env"
    source_bucket    = var.restore_source_bucket
    source_path      = "db"
    source_endpoint  = var.bucket_endpoint
    source_region    = var.bucket_region
    drill_bucket     = var.bucket_name
    age_key_file     = "/etc/budget-planner/litestream-age.key"
  }) : ""

  ghcr_auth_b64 = base64encode("deploy:${var.ghcr_pull_pat}")

  user_data = templatefile("${path.module}/../../cloud-init/bootstrap.yaml.tpl", {
    hostname                    = var.hostname
    operator_ssh_pubkey         = var.operator_ssh_pub
    github_deploy_pubkey        = var.deploy_ssh_pub
    scw_access_key              = var.scw_access_key
    scw_secret_key              = var.scw_secret_key
    ghcr_auth_b64               = local.ghcr_auth_b64
    docker_compose_rendered     = local.docker_compose_rendered
    caddyfile_rendered          = local.caddyfile_rendered
    litestream_rendered         = local.litestream_rendered
    litestream_restore_rendered = local.litestream_restore_rendered
    age_identity                = var.litestream_age_identity
    deploy_script_rendered      = local.deploy_script_rendered
    enable_restore_helper       = var.enable_restore_helper
    restore_script_rendered     = local.restore_script_rendered
    restore_access_key          = var.scw_access_key_restore
    restore_secret_key          = var.scw_secret_key_restore
    tailscale_authkey           = var.tailscale_authkey
    tailscale_hostname          = var.tailscale_hostname
    tailscale_tag               = var.tailscale_tag
  })
}
