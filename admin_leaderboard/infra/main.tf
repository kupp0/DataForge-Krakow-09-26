# ==============================================================================
# Disneyland Hackathon: Admin Leaderboard & Spanner Federation Infrastructure
# Project: dataforge26krk-6725 (Admin)
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

# --- 1. Enable Required Admin APIs ---
resource "google_project_service" "admin_apis" {
  for_each = toset([
    "spanner.googleapis.com",
    "bigquery.googleapis.com",
    "bigqueryconnection.googleapis.com",
    "monitoring.googleapis.com"
  ])
  project            = var.admin_project_id
  service            = each.key
  disable_on_destroy = false
}

# --- 2. BigQuery Admin Analytics Dataset ---
resource "google_bigquery_dataset" "admin_analytics" {
  dataset_id  = "admin_leaderboard"
  location    = var.region
  project     = var.admin_project_id
  friendly_name = "Disneyland Hackathon Admin Leaderboard"
  description = "Centralized analytics, participant telemetry, and reporting views"
  depends_on  = [google_project_service.admin_apis]
}

# --- 3. Centralized BigQuery Spanner Connection ---
resource "google_bigquery_connection" "spanner_federated_conn" {
  connection_id = "spanner_federated_conn"
  location      = var.region
  project       = var.admin_project_id
  friendly_name = "Spanner Central Federated Connector"
  description   = "Cross-project connector allowing BigQuery in 6725 to query Spanner across all participant projects"
  cloud_resource {}
  depends_on    = [google_project_service.admin_apis]
}

# Mitigate service account creation delay
resource "time_sleep" "wait_for_conn_sa" {
  create_duration = "15s"
  depends_on      = [google_bigquery_connection.spanner_federated_conn]
}

# --- 4. Cross-Project IAM Grants for BigQuery Connection SA ---
resource "google_project_iam_member" "conn_spanner_reader" {
  for_each = toset(var.participant_projects)
  project  = each.value
  role     = "roles/spanner.admin"
  member   = "serviceAccount:${google_bigquery_connection.spanner_federated_conn.cloud_resource[0].service_account_id}"
  depends_on = [time_sleep.wait_for_conn_sa]
}

resource "google_project_iam_member" "conn_monitoring_viewer" {
  for_each = toset(var.participant_projects)
  project  = each.value
  role     = "roles/monitoring.viewer"
  member   = "serviceAccount:${google_bigquery_connection.spanner_federated_conn.cloud_resource[0].service_account_id}"
  depends_on = [time_sleep.wait_for_conn_sa]
}

# Ensure cross-project IAM propagation before attaching external schemas
resource "time_sleep" "wait_for_iam_propagation" {
  create_duration = "45s"
  depends_on      = [
    google_project_iam_member.conn_spanner_reader,
    google_project_iam_member.conn_monitoring_viewer
  ]
}

# --- 5. Register 24 Spanner Databases as External Datasets in Project 6725 ---
resource "google_bigquery_dataset" "participant_spanner_dataset" {
  for_each    = toset(var.participant_projects)
  dataset_id  = "spanner_user_${substr(each.value, length(each.value) - 4, 4)}"
  location    = var.region
  project     = var.admin_project_id
  friendly_name = "Spanner Schema: ${each.value}"
  description   = "External federated dataset pointing to ${each.value}/instances/${var.spanner_instance_name}/databases/${var.spanner_database_name}"

  external_dataset_reference {
    external_source = "google-cloudspanner:/projects/${each.value}/instances/${var.spanner_instance_name}/databases/${var.spanner_database_name}"
    connection      = google_bigquery_connection.spanner_federated_conn.id
  }

  depends_on = [time_sleep.wait_for_iam_propagation]
}

# --- 6. Centralized Union & Telemetry Views in Project 6725 ---

# View 1: Dynamic discovery of all tables created across all 24 participant external schemas
resource "google_bigquery_table" "v_all_participant_tables" {
  dataset_id          = google_bigquery_dataset.admin_analytics.dataset_id
  table_id            = "v_all_participant_tables"
  project             = var.admin_project_id
  deletion_protection = false

  view {
    use_legacy_sql = false
    query          = <<-EOT
      SELECT 
        table_catalog, 
        table_schema, 
        table_name, 
        table_type,
        REGEXP_EXTRACT(table_schema, r'spanner_user_(\d+)') AS participant_short_id
      FROM `${var.admin_project_id}.region-${var.region}.INFORMATION_SCHEMA.TABLES`
      WHERE table_schema LIKE 'spanner_user_%'
    EOT
  }

  depends_on = [google_bigquery_dataset.participant_spanner_dataset]
}

# View 2: Aggregated summary view mapping participant cities to DDL completion
resource "google_bigquery_table" "v_participant_tables_summary" {
  dataset_id          = google_bigquery_dataset.admin_analytics.dataset_id
  table_id            = "v_participant_tables_summary"
  project             = var.admin_project_id
  deletion_protection = false

  view {
    use_legacy_sql = false
    query          = <<-EOT
      WITH participants AS (
        SELECT 'dataforge26krk-6701' AS project_id, 'Tokyo' AS city, 'spanner_user_6701' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6702' AS project_id, 'London' AS city, 'spanner_user_6702' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6703' AS project_id, 'Paris' AS city, 'spanner_user_6703' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6704' AS project_id, 'New York' AS city, 'spanner_user_6704' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6705' AS project_id, 'Sydney' AS city, 'spanner_user_6705' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6706' AS project_id, 'Berlin' AS city, 'spanner_user_6706' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6707' AS project_id, 'Rome' AS city, 'spanner_user_6707' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6708' AS project_id, 'Madrid' AS city, 'spanner_user_6708' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6709' AS project_id, 'Toronto' AS city, 'spanner_user_6709' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6710' AS project_id, 'Singapore' AS city, 'spanner_user_6710' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6711' AS project_id, 'Seoul' AS city, 'spanner_user_6711' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6712' AS project_id, 'Amsterdam' AS city, 'spanner_user_6712' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6713' AS project_id, 'San Francisco' AS city, 'spanner_user_6713' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6714' AS project_id, 'Dubai' AS city, 'spanner_user_6714' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6715' AS project_id, 'Vienna' AS city, 'spanner_user_6715' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6716' AS project_id, 'Zurich' AS city, 'spanner_user_6716' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6717' AS project_id, 'Stockholm' AS city, 'spanner_user_6717' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6718' AS project_id, 'Chicago' AS city, 'spanner_user_6718' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6719' AS project_id, 'Los Angeles' AS city, 'spanner_user_6719' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6720' AS project_id, 'Warsaw' AS city, 'spanner_user_6720' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6721' AS project_id, 'Prague' AS city, 'spanner_user_6721' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6722' AS project_id, 'Dublin' AS city, 'spanner_user_6722' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6723' AS project_id, 'Oslo' AS city, 'spanner_user_6723' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6724' AS project_id, 'Copenhagen' AS city, 'spanner_user_6724' AS dataset_id UNION ALL
        SELECT 'dataforge26krk-6725' AS project_id, 'Helsinki (Facilitator)' AS city, 'spanner_user_6725' AS dataset_id
      ),
      tables AS (
        SELECT 
          table_schema, 
          table_name 
        FROM `${var.admin_project_id}.region-${var.region}.INFORMATION_SCHEMA.TABLES`
        WHERE table_schema LIKE 'spanner_user_%'
      )
      SELECT 
        p.city,
        p.project_id,
        p.dataset_id,
        COUNT(t.table_name) AS total_tables_created,
        STRING_AGG(t.table_name, ', ' ORDER BY t.table_name) AS tables_list,
        COALESCE(LOGICAL_OR(LOWER(t.table_name) = 'disneylandpark'), false) AS has_disneylandpark,
        COALESCE(LOGICAL_OR(LOWER(t.table_name) = 'attraction'), false) AS has_attraction,
        COALESCE(LOGICAL_OR(LOWER(t.table_name) = 'path'), false) AS has_path,
        COALESCE(LOGICAL_OR(LOWER(t.table_name) LIKE '%run%' OR LOWER(t.table_name) LIKE '%execution%'), false) AS has_runs_challenge
      FROM participants p
      LEFT JOIN tables t ON p.dataset_id = t.table_schema
      GROUP BY p.city, p.project_id, p.dataset_id
      ORDER BY total_tables_created DESC, p.city ASC
    EOT
  }

  depends_on = [google_bigquery_dataset.participant_spanner_dataset]
}


