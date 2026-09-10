# ==============================================================================
# Dynamic Root Module - Stitched by Hackathon Scaffolder
# ==============================================================================

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">= 5.0"
    }
  }
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# 1. Base Core Infrastructure
module "core" {
  source       = "./00-core-infra"
  project_id   = var.project_id
  region       = var.region
  iap_member   = var.iap_member
}

# 2.1 Lab Module: One Million Vectors, Zero Loops (AlloyDB Vectors)
module "lab_alloydb_vectors" {
  source                    = "./labs/lab01_alloydb_vectors/infra"
  project_id                = var.project_id
  region                    = var.region
  iap_member                = var.iap_member
  vpc_id                    = module.core.vpc_id
  private_vpc_connection_id = module.core.private_vpc_connection_id
  alloydb_instance_cpu_count = var.alloydb_vectors_alloydb_instance_cpu_count
  alloydb_password = var.alloydb_vectors_alloydb_password

  depends_on = [
    module.core
  ]
}

# 2.2 Lab Module: Disneyland Agentic Codelab (Spanner & BigQuery)
module "lab_spanner_disneyland" {
  source                    = "./labs/lab02_spanner_disneyland/infra"
  project_id                = var.project_id
  region                    = var.region
  iap_member                = var.iap_member
  vpc_id                    = module.core.vpc_id
  private_vpc_connection_id = module.core.private_vpc_connection_id

  depends_on = [
    module.core
  ]
}

# 3. Dynamic Least-Privilege Lab IAM Roles
resource "google_project_iam_member" "lab_roles" {
  for_each = toset([
    "roles/mcp.toolUser",
    "roles/spanner.admin"
  ])
  project = var.project_id
  role    = each.key
  member  = var.iap_member
}
