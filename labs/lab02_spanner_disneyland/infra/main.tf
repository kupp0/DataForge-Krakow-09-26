# ==============================================================================
# DACH Summit 2026: Lab 2 Spanner Disneyland Federated Setup (Decoupled)
# ==============================================================================

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
    time = {
      source  = "hashicorp/time"
      version = ">= 0.11.0"
    }
  }
}

# Retrieve project number dynamically
data "google_project" "project" {
  project_id = var.project_id
}

#--- 1. Enable Required APIs for this Lab ---
resource "google_project_service" "enabled_apis" {
  for_each = toset([
    "spanner.googleapis.com",
    "bigquery.googleapis.com",
    "bigqueryconnection.googleapis.com",
    "aiplatform.googleapis.com",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com"
  ])
  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

#--- 2. Cloud Spanner Setup ---
resource "google_spanner_instance" "disneyland" {
  name             = "disneyland"
  project          = var.project_id
  config           = "regional-${var.region}"
  display_name     = "Disneyland AI Agents"
  edition          = "ENTERPRISE"
  processing_units = 100
  force_destroy    = true
  depends_on       = [google_project_service.enabled_apis]
}

#--- 2b. Spanner Service Agent IAM for Vertex AI Integration ---
resource "google_project_iam_member" "spanner_vertex_user" {
  project    = var.project_id
  role       = "roles/aiplatform.user"
  member     = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-spanner.iam.gserviceaccount.com"
  depends_on = [google_project_service.enabled_apis, google_spanner_instance.disneyland]
}

resource "google_project_iam_member" "spanner_service_agent" {
  project    = var.project_id
  role       = "roles/spanner.serviceAgent"
  member     = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-spanner.iam.gserviceaccount.com"
  depends_on = [google_project_service.enabled_apis, google_spanner_instance.disneyland]
}

resource "google_spanner_database" "agent_lab" {
  instance            = google_spanner_instance.disneyland.name
  name                = "agent-lab"
  project             = var.project_id
  database_dialect    = "GOOGLE_STANDARD_SQL"
  deletion_protection = false
}

#--- 3. BigQuery Setup & Connection ---
resource "google_bigquery_dataset" "disney_dataset" {
  dataset_id = "disney"
  location   = var.region
  project    = var.project_id
  depends_on = [google_project_service.enabled_apis]
}

resource "google_bigquery_connection" "spanner_conn" {
  connection_id = "spanner_conn"
  location      = var.region
  project       = var.project_id
  friendly_name = "Spanner Connector"
  cloud_resource {}
  depends_on    = [google_project_service.enabled_apis]
}

# Mitigates GCP registration delay
resource "time_sleep" "wait_for_connection_sa" {
  create_duration = "15s"
  depends_on      = [google_bigquery_connection.spanner_conn]
}

#--- 4. Authoritative IAM Admin Permissions ---
resource "google_project_iam_binding" "spanner_admin_bridge" {
  project = var.project_id
  role    = "roles/spanner.admin"
  members = ["serviceAccount:${google_bigquery_connection.spanner_conn.cloud_resource[0].service_account_id}"]
  
  depends_on = [time_sleep.wait_for_connection_sa]
}

resource "time_sleep" "wait_for_iam" {
  create_duration = "60s"
  depends_on      = [
    google_project_iam_binding.spanner_admin_bridge,
    google_spanner_database.agent_lab
  ]
}

#--- 5. BigQuery External Dataset (The Spanner Bridge) ---
resource "google_bigquery_dataset" "spanner_external_dataset" {
  dataset_id  = "disneyland_spanner_external"
  location    = var.region
  project     = var.project_id  
  
  external_dataset_reference {
    external_source = "google-cloudspanner:/projects/${var.project_id}/instances/${google_spanner_instance.disneyland.name}/databases/${google_spanner_database.agent_lab.name}"
    connection      = google_bigquery_connection.spanner_conn.id
  }
  
  depends_on = [time_sleep.wait_for_iam]
}

#--- 6. Cloud Run & Cloud Build Participant and Service Account IAM ---
resource "google_project_iam_member" "participant_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = var.iap_member
}

resource "google_project_iam_member" "participant_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = var.iap_member
}

resource "google_project_iam_member" "compute_sa_cloud_run_roles" {
  for_each = toset([
    "roles/storage.admin",
    "roles/logging.logWriter",
    "roles/artifactregistry.writer"
  ])

  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}
