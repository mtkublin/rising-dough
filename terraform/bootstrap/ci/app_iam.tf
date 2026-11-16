# T-D103 / ADR-0104: the env stacks' IAM identities live here, so no CI key needs
# IAMManager. Prod resources were imported from the prod state (keys unchanged,
# cloud-init unchanged); drill was created here. The env stacks receive the ids and
# keys as GitHub environment secrets (APP_*, RESTORE_READER_APPLICATION_ID).

# Litestream + first-boot identity per env (moved from terraform/modules/iam).
module "app_prod" {
  source = "./modules/app_iam"

  name_prefix         = "budget-planner-prod"
  scaleway_project_id = var.prod_project_id
}

module "app_drill" {
  source = "./modules/app_iam"

  name_prefix         = "budget-planner-drill"
  scaleway_project_id = var.drill_project_id
}

# Read-only identity for the restore drill (moved from terraform/modules/restore_reader).
module "restore_reader" {
  source = "./modules/restore_reader"

  name_prefix         = "budget-planner-prod"
  scaleway_project_id = var.prod_project_id
}
