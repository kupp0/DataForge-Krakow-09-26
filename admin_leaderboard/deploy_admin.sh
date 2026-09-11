#!/usr/bin/env bash
# ==============================================================================
# Master Admin Deployment Script: Disneyland Spanner Federation & Leaderboard
# Admin Project: dataforge26krk-6725
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
INFRA_DIR="${SCRIPT_DIR}/infra"
DASHBOARD_DIR="${SCRIPT_DIR}/dashboard"

ADMIN_PROJECT="dataforge26krk-6725"
REGION="europe-west3"

echo "================================================================="
echo "  🏰 Disneyland Spanner Admin Hub: Project ${ADMIN_PROJECT}       "
echo "================================================================="

# 1. Check GCloud Authentication
echo "🔍 Checking gcloud active account..."
ACTIVE_ACCOUNT=$(gcloud config get-value account 2>/dev/null || true)
if [ -z "${ACTIVE_ACCOUNT}" ]; then
    echo "❌ Error: No active gcloud account detected. Run 'gcloud auth login' or 'gcloud auth application-default login'."
    exit 1
fi
echo "✅ Logged in as: ${ACTIVE_ACCOUNT}"

# 2. Provision Terraform Infrastructure
echo "🚀 Initializing Terraform in ${INFRA_DIR}..."
terraform -chdir="${INFRA_DIR}" init

echo "⚙️  Applying Terraform for Project ${ADMIN_PROJECT}..."
terraform -chdir="${INFRA_DIR}" apply -auto-approve \
    -var="admin_project_id=${ADMIN_PROJECT}" \
    -var="region=${REGION}"

echo "✅ Admin BigQuery Connection and 24 External Datasets successfully deployed!"

# 3. Print outputs
CONN_ID=$(terraform -chdir="${INFRA_DIR}" output -raw connection_id 2>/dev/null || echo "spanner_federated_conn")
CONN_SA=$(terraform -chdir="${INFRA_DIR}" output -raw connection_service_account 2>/dev/null || echo "")

echo "-----------------------------------------------------------------"
echo "📋 Connection ID: ${CONN_ID}"
echo "🔑 Connection SA: ${CONN_SA}"
echo "-----------------------------------------------------------------"
echo "🎉 Admin setup complete! You can now launch the dashboard by running:"
echo "   ${DASHBOARD_DIR}/run.sh"
echo "================================================================="

