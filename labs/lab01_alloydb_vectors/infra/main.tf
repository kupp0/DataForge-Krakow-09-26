# ==============================================================================
# DACH Summit 2026: Lab 1 AlloyDB & Vertex AI Core Infrastructure Setup (Decoupled)
# ==============================================================================

# Retrieve project number dynamically
data "google_project" "project" {
  project_id = var.project_id
}

#--- 1. Enable Required GCP APIs for this Lab ---
resource "google_project_service" "alloydb_apis" {
  for_each = toset([
    "alloydb.googleapis.com",
    "aiplatform.googleapis.com",
    "cloudaicompanion.googleapis.com"
  ])
  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

#--- 2. IAM Policy Bindings for Vertex AI integration ---
# Grants Vertex AI User role to the AlloyDB Service Agent to generate vector embeddings
resource "google_project_iam_member" "alloydb_vertex_user" {
  project    = var.project_id
  role       = "roles/aiplatform.user"
  member     = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-alloydb.iam.gserviceaccount.com"
  depends_on = [google_project_service.alloydb_apis, google_alloydb_instance.primary]
}

#--- 3. AlloyDB Cluster Setup ---
resource "google_alloydb_cluster" "default" {
  cluster_id = "search-cluster"
  project    = var.project_id
  location   = var.region
  deletion_protection = false

  network_config {
    network = var.vpc_id
  }

  initial_user {
    password = var.alloydb_password
  }

  depends_on = [
    google_project_service.alloydb_apis
  ]
}

#--- 4. AlloyDB Instance Setup with database flags ---
resource "google_alloydb_instance" "primary" {
  cluster       = google_alloydb_cluster.default.name
  instance_id   = "search-primary"
  instance_type = "PRIMARY"

  machine_config {
    cpu_count = var.alloydb_instance_cpu_count
  }

  database_flags = {
    "alloydb.iam_authentication"                               = "on"
    "google_ml_integration.enable_model_support"               = "on"
    "google_ml_integration.enable_faster_embedding_generation" = "on"
    "alloydb_ai_nl.enabled"                                    = "on"
    "google_ml_integration.enable_ai_query_engine"             = "on"
    "scann.enable_zero_knob_index_creation"                    = "on"
    "password.enforce_complexity"                              = "on"
    "google_db_advisor.enable_auto_advisor"                    = "on"
    "google_db_advisor.auto_advisor_schedule"                  = "EVERY 24 HOURS"
    "parameterized_views.enabled"                              = "on"
  }

  depends_on = [google_alloydb_cluster.default]
}

#--- 4.5. Enable Data API on AlloyDB primary instance ---
# resource "null_resource" "enable_alloydb_data_api" {
#   provisioner "local-exec" {
#     command = "curl -s -X PATCH -H \"Authorization: Bearer $(gcloud auth print-access-token)\" -H \"Content-Type: application/json\" \"https://alloydb.googleapis.com/v1alpha/projects/${var.project_id}/locations/${var.region}/clusters/${google_alloydb_cluster.default.cluster_id}/instances/${google_alloydb_instance.primary.instance_id}?updateMask=dataApiAccess\" -d '{\"dataApiAccess\": \"ENABLED\"}'"
#   }
# 
#   depends_on = [google_alloydb_instance.primary]
# }

#--- 5. AlloyDB IAM User Setup ---
resource "google_alloydb_user" "iam_user" {
  cluster        = google_alloydb_cluster.default.name
  user_id        = replace(var.iap_member, "user:", "")
  user_type      = "ALLOYDB_IAM_USER"
  database_roles = ["alloydbsuperuser", "alloydbiamuser"]

  lifecycle {
    ignore_changes = [database_roles]
  }
  
  depends_on = [google_alloydb_cluster.default, google_alloydb_instance.primary]
}
