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
  })

  deploy_script_rendered = templatefile("${path.module}/../../cloud-init/bin/deploy-budget-planner.tpl", {
    owner = var.github_owner
  })

  ghcr_auth_b64 = base64encode("deploy:${var.ghcr_pull_pat}")

  user_data = templatefile("${path.module}/../../cloud-init/bootstrap.yaml.tpl", {
    hostname                = var.hostname
    operator_ssh_pubkey     = var.operator_ssh_pub
    github_deploy_pubkey    = var.deploy_ssh_pub
    scw_access_key          = var.scw_access_key
    scw_secret_key          = var.scw_secret_key
    ghcr_auth_b64           = local.ghcr_auth_b64
    docker_compose_rendered = local.docker_compose_rendered
    caddyfile_rendered      = local.caddyfile_rendered
    litestream_rendered     = local.litestream_rendered
    deploy_script_rendered  = local.deploy_script_rendered
  })
}
