provider "scaleway" {
  project_id      = var.scaleway_project_id
  organization_id = var.scaleway_organization_id
  region          = var.scaleway_region
  zone            = var.scaleway_zone
}

provider "random" {}
