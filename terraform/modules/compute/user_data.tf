# ----------------------------------------------------------------------------
# Host state assembly (ADR-0111).
#
# Three instance metadata keys, all in scaleway_instance_server.user_data:
#   cloud-init  fixed bootstrap (users, Tailscale, Docker, firewall, the agent
#               loader + timer); runs once at first boot.
#   bp-agent    the host agent (terraform/host/agent/bp_agent.py).
#   bp-config   everything the agent converges to: managed files, image ref,
#               cosign policy. Updated in place by every apply; the agent picks
#               it up within ~30 s (no reboot, no SSH).
# Each file template is rendered independently so indentation stays safe and
# CI can lint each one (`caddy validate`, YAML parse).
# ----------------------------------------------------------------------------

locals {
  # T-Q238 (Q-040): the verified signing identity is build.yml run from main or
  # from a release tag. A signature from any other ref (a PR or attacker branch
  # that reached the reusable build) is rejected on prod. Drill hosts verify
  # branch builds, so they accept any branch or tag ref of the same workflow.
  cosign_identity_prefix  = "^https://github\\.com/${var.github_owner}/${var.github_repo}/\\.github/workflows/build\\.yml@"
  cosign_ref_regexp_prod  = "(refs/heads/main|refs/tags/v[0-9][0-9A-Za-z.+-]*)$"
  cosign_ref_regexp_drill = "refs/(heads|tags)/.+$"
  cosign_identity_regexp  = "${local.cosign_identity_prefix}${var.allow_branch_builds ? local.cosign_ref_regexp_drill : local.cosign_ref_regexp_prod}"

  image_repo  = "ghcr.io/${var.github_owner}/budget-planner"
  compose_dir = "/etc/budget-planner"

  docker_compose_rendered = templatefile("${path.module}/../../cloud-init/compose/docker-compose.yml.tpl", {
    app_image              = "${local.image_repo}:${var.app_image_ref}"
    cookie_secret          = var.cookie_secret
    trusted_hosts          = var.trusted_hosts_csv
    hostname               = var.hostname
    admin_email            = var.admin_email
    admin_initial_password = var.admin_password
    backup_max_age_days    = var.backup_max_age_days
    scw_access_key         = var.scw_access_key
    scw_secret_key         = var.scw_secret_key
    tailnet_only           = var.tailnet_only
    allow_empty_db         = var.allow_empty_db
  })

  caddyfile_rendered = templatefile("${path.module}/../../cloud-init/compose/Caddyfile.tpl", {
    hostname     = var.hostname
    tailnet_only = var.tailnet_only
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

  # T-D41a: drill-only restore helper. Empty string on other environments.
  restore_script_rendered = var.enable_restore_helper ? templatefile("${path.module}/../../cloud-init/bin/restore-from-prod.tpl", {
    compose_dir      = local.compose_dir
    restore_env_file = "${local.compose_dir}/restore-source.env"
    hostname         = var.hostname
    source_bucket    = var.restore_source_bucket
    source_path      = "db"
    source_endpoint  = var.bucket_endpoint
    source_region    = var.bucket_region
    drill_bucket     = var.bucket_name
    age_key_file     = "${local.compose_dir}/restore-source-age.key"
  }) : ""

  # T-Q306(c) / ADR-0149: drill-only demo seed helper. Needs no prod credential, so it
  # has its own switch, independent of enable_restore_helper. Empty string elsewhere.
  seed_script_rendered = var.enable_seed_helper ? templatefile("${path.module}/../../cloud-init/bin/seed-demo.tpl", {
    compose_dir = local.compose_dir
    hostname    = var.hostname
  }) : ""

  docker_config_json = jsonencode({
    auths = { "ghcr.io" = { auth = base64encode("deploy:${var.ghcr_pull_pat}") } }
  })

  # Every file the agent owns. `restart`: compose services to restart when the
  # file changes (bind-mounted config that `compose up -d` does not notice).
  managed_files = concat(
    [
      { path = "${local.compose_dir}/docker-compose.yml", mode = "0600", content = local.docker_compose_rendered, restart = [] },
      { path = "${local.compose_dir}/Caddyfile", mode = "0644", content = local.caddyfile_rendered, restart = ["caddy"] },
      { path = "${local.compose_dir}/litestream.yml", mode = "0644", content = local.litestream_rendered, restart = ["litestream"] },
      # T-D56 / ADR-0078 §3: restore-only config + age identity (ADR-0069 secret-file pattern).
      { path = "${local.compose_dir}/litestream-restore.yml", mode = "0644", content = local.litestream_restore_rendered, restart = [] },
      # T-D156 / ADR-0127: restore entrypoint (empty-DB guard, restore report).
      { path = "${local.compose_dir}/litestream-restore.sh", mode = "0755", content = file("${path.module}/../../cloud-init/compose/litestream-restore.sh"), restart = [] },
      { path = "${local.compose_dir}/litestream-age.key", mode = "0600", content = "${trimspace(var.litestream_age_identity)}\n", restart = ["litestream"] },
      # T-D136 / ADR-0114: replicate entrypoint (identity export, one-time new generation).
      { path = "${local.compose_dir}/litestream-entrypoint.sh", mode = "0755", content = file("${path.module}/../../cloud-init/compose/litestream-entrypoint.sh"), restart = ["litestream"] },
      # T-D144 / ADR-0119: replication freshness probe (status file for /health/replication).
      { path = "${local.compose_dir}/litestream-replication-probe.sh", mode = "0755", content = file("${path.module}/../../cloud-init/compose/litestream-replication-probe.sh"), restart = ["litestream-probe"] },
      { path = "${local.compose_dir}/litestream.env", mode = "0600", content = "SCW_ACCESS_KEY=${var.scw_access_key}\nSCW_SECRET_KEY=${var.scw_secret_key}\n", restart = ["litestream"] },
      # Operator `sudo docker compose pull` uses root's registry auth.
      { path = "/root/.docker/config.json", mode = "0600", content = "${local.docker_config_json}\n", restart = [] },
      { path = "/etc/logrotate.d/caddy-access", mode = "0644", content = file("${path.module}/../../cloud-init/compose/caddy-access.logrotate"), restart = [] },
    ],
    var.enable_restore_helper ? [
      # T-D41a: drill-only read-only credential for the PROD replica + helper.
      { path = "${local.compose_dir}/restore-source.env", mode = "0600", content = "RESTORE_ACCESS_KEY_ID=${var.scw_access_key_restore}\nRESTORE_SECRET_ACCESS_KEY=${var.scw_secret_key_restore}\n", restart = [] },
      # ADR-0135: the PROD replica identity, never the host's own litestream-age.key.
      { path = "${local.compose_dir}/restore-source-age.key", mode = "0600", content = "${trimspace(var.restore_source_age_identity)}\n", restart = [] },
      { path = "/usr/local/bin/restore-from-prod", mode = "0755", content = local.restore_script_rendered, restart = [] },
    ] : [],
    var.enable_seed_helper ? [
      { path = "/usr/local/bin/seed-demo", mode = "0755", content = local.seed_script_rendered, restart = [] },
    ] : [],
  )

  agent_source = file("${path.module}/../../host/agent/bp_agent.py")

  # The agent applies a generation once; the hash covers the agent too, so a
  # new agent version re-runs the apply.
  host_config_body = {
    schema       = 1
    compose_file = "${local.compose_dir}/docker-compose.yml"
    image = {
      ref          = "${local.image_repo}:${var.app_image_ref}"
      previous_ref = var.app_image_previous_ref == "" ? "" : "${local.image_repo}:${var.app_image_previous_ref}"
      container    = "budget-planner-app"
    }
    ready = {
      url     = "https://${var.hostname}/ready"
      resolve = "${var.hostname}:443:127.0.0.1"
    }
    docker_config_json = local.docker_config_json
    cosign = {
      version         = var.cosign_version
      url             = "https://github.com/sigstore/cosign/releases/download/${var.cosign_version}/cosign-linux-amd64"
      sha256          = var.cosign_sha256
      identity_regexp = local.cosign_identity_regexp
      issuer          = "https://token.actions.githubusercontent.com"
    }
    # T-Q238 (Q-040, ADR-0099 amendment 2026-11-21): a sha-* image is accepted
    # only when its commit is an ancestor of main (host agent, GitHub compare
    # API). Drills build from arbitrary branches, so the check is off there.
    ancestry = {
      enabled = !var.allow_branch_builds
      repo    = "${var.github_owner}/${var.github_repo}"
      branch  = "main"
    }
    files = [for f in local.managed_files : merge(f, { owner = "root", group = "root" })]
  }
  # A sha256 over the config reveals nothing about the secrets inside it; the
  # CI monitor compares it with the status the host reports.
  host_config_generation = nonsensitive(sha256(join("\n", [jsonencode(local.host_config_body), sha256(local.agent_source)])))
  host_config_json       = jsonencode(merge(local.host_config_body, { generation = local.host_config_generation }))

  cloud_init_rendered = templatefile("${path.module}/../../cloud-init/bootstrap.yaml.tpl", {
    hostname              = var.hostname
    operator_ssh_pubkey   = var.operator_ssh_pub
    ci_ssh_pubkey         = var.ci_ssh_pub
    scw_access_key        = var.scw_access_key
    scw_secret_key        = var.scw_secret_key
    tailscale_authkey     = var.tailscale_authkey
    tailscale_hostname    = var.tailscale_hostname
    tailscale_tag         = var.tailscale_tag
    break_glass_ssh_cidrs = var.break_glass_ssh_cidrs
    console_password_hash = var.console_password_hash
    boot_log_upload       = var.boot_log_upload
    bucket_name           = var.bucket_name
    bucket_region         = var.bucket_region
    tailnet_only          = var.tailnet_only
  })

  # ADR-0111: the provider writes the whole map on every change and reads every
  # key back, so all keys live here (no separate `cloud_init` attribute).
  user_data = {
    "cloud-init" = local.cloud_init_rendered
    "bp-agent"   = local.agent_source
    "bp-config"  = local.host_config_json
  }
}
