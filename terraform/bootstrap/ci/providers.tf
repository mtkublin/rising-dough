# Credentials come from SCW_ACCESS_KEY / SCW_SECRET_KEY (the operator's
# break-glass org-admin key, applied locally; ADR-0100).
provider "scaleway" {
  project_id      = var.prod_project_id
  organization_id = var.scaleway_organization_id
  region          = var.region
}
