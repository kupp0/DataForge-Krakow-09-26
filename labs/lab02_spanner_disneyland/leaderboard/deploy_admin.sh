#!/usr/bin/env bash
# ==============================================================================
# Master Admin Deployment Script: Disneyland Spanner Federation & Leaderboard
# Admin Project: dataforge26krk-6725
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
INFRA_DIR="${SCRIPT_DIR}/infra"
DASHBOARD_DIR="${SCRIPT_DIR}/dashboard"

# 1. Check GCloud Authentication
echo "🔍 Checking gcloud active account..."
ACTIVE_ACCOUNT=$(gcloud config get-value account 2>/dev/null || true)
if [ -z "${ACTIVE_ACCOUNT}" ]; then
    echo "❌ Error: No active gcloud account detected. Run 'gcloud auth login' or 'gcloud auth application-default login'."
    exit 1
fi
echo "✅ Logged in as: ${ACTIVE_ACCOUNT}"

# 2. Dynamically Resolve Admin Project
ADMIN_PROJECT="${1:-${ADMIN_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || "")}}"
PROJECTS_FILE="${ROOT_DIR}/projects.txt"

if [ -z "${ADMIN_PROJECT}" ] && [ -f "${PROJECTS_FILE}" ]; then
    ADMIN_PROJECT=$(awk -F',' '!/^#/ && NF>=4 {gsub(/ /, "", $1); last=$1} END {print last}' "${PROJECTS_FILE}")
fi

if [ -z "${ADMIN_PROJECT}" ]; then
    echo "❌ Error: Could not resolve admin project ID. Provide as \$1 or set via gcloud config set project [ID]."
    exit 1
fi

REGION="${REGION:-europe-west3}"

echo "================================================================="
echo "  🏰 Lab 2: Disneyland Spanner Admin Hub: Project ${ADMIN_PROJECT}  "
echo "================================================================="

# 3. Dynamically Parse Participant Projects from projects.txt
if [ ! -f "${PROJECTS_FILE}" ]; then
    echo "❌ Error: projects.txt not found at ${PROJECTS_FILE}"
    exit 1
fi

PROJECTS_JSON=$(awk -F',' '!/^#/ && NF>=4 {gsub(/ /, "", $1); if ($1 != "") printf "\"%s\",", $1}' "${PROJECTS_FILE}" | sed 's/,$//')
PROJECT_COUNT=$(awk -F',' '!/^#/ && NF>=4 {c++} END {print c}' "${PROJECTS_FILE}")

echo "📋 Discovered ${PROJECT_COUNT} project(s) in ${PROJECTS_FILE}."

# 4. Provision Terraform Infrastructure
echo "🚀 Initializing Terraform in ${INFRA_DIR}..."
terraform -chdir="${INFRA_DIR}" init

echo "⚙️  Applying Terraform for Admin Project ${ADMIN_PROJECT} across ${PROJECT_COUNT} participant projects..."
terraform -chdir="${INFRA_DIR}" apply -auto-approve \
    -var="admin_project_id=${ADMIN_PROJECT}" \
    -var="region=${REGION}" \
    -var="participant_projects=[${PROJECTS_JSON}]"

echo "✅ Admin BigQuery Connection and External Datasets successfully deployed!"

# 5. Print outputs
CONN_ID=$(terraform -chdir="${INFRA_DIR}" output -raw connection_id 2>/dev/null || echo "spanner_federated_conn")
CONN_SA=$(terraform -chdir="${INFRA_DIR}" output -raw connection_service_account 2>/dev/null || echo "")

echo "-----------------------------------------------------------------"
echo "📋 Connection ID: ${CONN_ID}"
echo "🔑 Connection SA: ${CONN_SA}"
echo "-----------------------------------------------------------------"
echo "🎉 Admin setup complete! You can now launch the dashboard by running:"
echo "   ${DASHBOARD_DIR}/run.sh"
echo "================================================================="

