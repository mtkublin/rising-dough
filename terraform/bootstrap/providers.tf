# Credentials come from SCW_ACCESS_KEY / SCW_SECRET_KEY in the environment.
provider "scaleway" {
  project_id      = var.scaleway_project_id
  organization_id = var.scaleway_organization_id
  region          = var.region
}
