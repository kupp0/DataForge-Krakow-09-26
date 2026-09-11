variable "admin_project_id" {
  description = "GCP Project ID for the administrator / leaderboard host"
  type        = string
  default     = "dataforge26krk-6725"
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
  default = [
    "dataforge26krk-6701",
    "dataforge26krk-6702",
    "dataforge26krk-6703",
    "dataforge26krk-6704",
    "dataforge26krk-6705",
    "dataforge26krk-6706",
    "dataforge26krk-6707",
    "dataforge26krk-6708",
    "dataforge26krk-6709",
    "dataforge26krk-6710",
    "dataforge26krk-6711",
    "dataforge26krk-6712",
    "dataforge26krk-6713",
    "dataforge26krk-6714",
    "dataforge26krk-6715",
    "dataforge26krk-6716",
    "dataforge26krk-6717",
    "dataforge26krk-6718",
    "dataforge26krk-6719",
    "dataforge26krk-6720",
    "dataforge26krk-6721",
    "dataforge26krk-6722",
    "dataforge26krk-6723",
    "dataforge26krk-6724",
    "dataforge26krk-6725"
  ]
}

