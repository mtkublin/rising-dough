provider "scaleway" {
  project_id      = var.scaleway_project_id
  organization_id = var.scaleway_organization_id
  region          = var.scaleway_region
  zone            = var.scaleway_zone
}

provider "random" {}

# T-D67 / ADR-0094: OAuth client (scope auth_keys:write, tags tag:prod/tag:drill).
# `tailnet` is omitted: it defaults to the tailnet that owns the OAuth client.
provider "tailscale" {
  oauth_client_id     = var.tailscale_oauth_client_id
  oauth_client_secret = var.tailscale_oauth_client_secret
  scopes              = ["auth_keys"]
}
