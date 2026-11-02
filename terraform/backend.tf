# Backend configuration is supplied per environment via:
#   terraform init -backend-config=envs/<env>/backend.hcl
#
# See terraform/README.md and ADR-0035 §4 for the state-bucket bootstrap.
terraform {
  backend "s3" {}
}
