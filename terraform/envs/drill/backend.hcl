bucket                      = "budget-planner-tfstate-drill-pl-waw"
key                         = "drill/terraform.tfstate"
endpoints                   = { s3 = "https://s3.pl-waw.scw.cloud" }
region                      = "pl-waw"
skip_credentials_validation = true
skip_region_validation      = true
skip_metadata_api_check     = true
skip_requesting_account_id  = true
skip_s3_checksum            = true
use_lockfile                = true
