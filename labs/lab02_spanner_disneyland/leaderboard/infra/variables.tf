variable "admin_project_id" {
  description = "GCP Project ID for the administrator / leaderboard host"
  type        = string
  default     = ""
}

variable "region" {
  description = "GCP Region for BigQuery and Spanner"
  type        = string
  default     = "europe-west3"
}

variable "spanner_instance_name" {
  description = "Cloud Spanner instance name in each participant project"
  type        = string
  default     = "disneyland"
}

variable "spanner_database_name" {
  description = "Cloud Spanner database name in each participant project"
  type        = string
  default     = "agent-lab"
}

variable "participant_projects" {
  description = "List of participant GCP project IDs"
  type        = list(string)
  default     = []
}

