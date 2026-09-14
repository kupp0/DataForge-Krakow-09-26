output "admin_project_id" {
  description = "Administrator project ID"
  value       = var.admin_project_id
}

output "connection_id" {
  description = "BigQuery Spanner Connection ID"
  value       = google_bigquery_connection.spanner_federated_conn.id
}

output "connection_service_account" {
  description = "Service Account used by the BigQuery Spanner Connection"
  value       = google_bigquery_connection.spanner_federated_conn.cloud_resource[0].service_account_id
}

output "external_dataset_ids" {
  description = "List of created external dataset IDs in admin project"
  value       = [for ds in google_bigquery_dataset.participant_spanner_dataset : ds.dataset_id]
}

