#!/bin/bash
set -e

# Install root requirements
if [ -f "requirements.txt" ]; then
    echo "Installing base requirements..."
    pip install --break-system-packages -r requirements.txt
fi

# Ensure user is authenticated
if [ -z "$(gcloud config get-value account 2>/dev/null)" ] || [ ! -f ~/.config/gcloud/application_default_credentials.json ]; then
    echo "🔑 Authenticating Google Cloud SDK and Application Default Credentials..."
    gcloud auth login --update-adc
else
    echo "✅ Already authenticated as $(gcloud config get-value account 2>/dev/null)"
fi




# Fetch project and location details
GCP_PROJECT_ID=$(gcloud config get-value project 2>/dev/null || echo "")
if [ -z "$GCP_PROJECT_ID" ]; then
    echo "❌ Error: No active gcloud project set. Please set it using 'gcloud config set project <PROJECT_ID>'." >&2
    exit 1
fi

# 🔓 Disable Domain Restricted Sharing Org Policy to allow public Cloud Run services (allUsers invoker)
echo "🔒 Disabling Domain Restricted Sharing Organization Policy..."
cat <<EOF > /tmp/allowed-sharing-policy.yaml
name: projects/${GCP_PROJECT_ID}/policies/iam.allowedPolicyMemberDomains
spec:
  rules:
  - allowAll: true
EOF
gcloud org-policies set-policy /tmp/allowed-sharing-policy.yaml --project="${GCP_PROJECT_ID}" --quiet &>/dev/null || true
rm -f /tmp/allowed-sharing-policy.yaml

PROJECT_NUMBER=$(gcloud projects describe "${GCP_PROJECT_ID}" --format="value(projectNumber)" 2>/dev/null)
GCP_LOCATION=$(gcloud alloydb instances list --cluster=search-cluster --format="value(location)" --limit=1 2>/dev/null || echo "")
if [ -z "$GCP_LOCATION" ]; then
    GCP_LOCATION="europe-west3"
fi

echo "🚀 Bootstrapping shared services, IAM, and storage configuration..."

# 1. Search Backend Service Account & IAM Roles
SA_EMAIL="search-backend-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
if ! gcloud iam service-accounts describe "${SA_EMAIL}" --project="${GCP_PROJECT_ID}" &>/dev/null; then
    echo "🤖 Creating search-backend-sa service account..."
    gcloud iam service-accounts create search-backend-sa \
        --display-name="Search Backend Service Account" \
        --project="${GCP_PROJECT_ID}"
else
    echo "✅ Service account search-backend-sa already exists."
fi

echo "🔑 Assigning roles to search-backend-sa..."
for role in \
    roles/alloydb.client \
    roles/logging.logWriter \
    roles/artifactregistry.repoAdmin \
    roles/serviceusage.serviceUsageConsumer \
    roles/aiplatform.user \
    roles/discoveryengine.editor \
    roles/storage.objectAdmin \
    roles/secretmanager.secretAccessor; do
    gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="${role}" \
        --condition=none &>/dev/null || true
done

# 2. Cloud Build & Compute service identity and roles
echo "🔌 Ensuring Cloud Build API is enabled..."
gcloud services enable cloudbuild.googleapis.com --project="${GCP_PROJECT_ID}" --quiet

echo "🛠️ Creating service identity for Cloud Build..."
gcloud services identity create --service=cloudbuild.googleapis.com --project="${GCP_PROJECT_ID}" --quiet &>/dev/null || true

echo "🔑 Assigning roles to Cloud Build service account..."
gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
    --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-cloudbuild.iam.gserviceaccount.com" \
    --role="roles/artifactregistry.repoAdmin" \
    --condition=none --quiet &>/dev/null || true

echo "🔑 Assigning roles to Default Compute service account..."
for role in \
    roles/storage.objectViewer \
    roles/artifactregistry.repoAdmin \
    roles/logging.logWriter; do
    gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
        --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
        --role="${role}" \
        --condition=none &>/dev/null || true
done



# 4. Artifact Registry & Storage Buckets
if ! gcloud artifacts repositories describe search-demo --location="${GCP_LOCATION}" --project="${GCP_PROJECT_ID}" &>/dev/null; then
    echo "📦 Creating Artifact Registry repository search-demo..."
    gcloud artifacts repositories create search-demo \
        --repository-format=docker \
        --location="${GCP_LOCATION}" \
        --description="Search Demo Docker Repository" \
        --project="${GCP_PROJECT_ID}" \
        --quiet
else
    echo "✅ Artifact Registry repository search-demo already exists."
fi

BUCKET_NAME="${GCP_PROJECT_ID}-search-demo-images"
if ! gcloud storage buckets describe "gs://${BUCKET_NAME}" &>/dev/null; then
    echo "🪣 Creating Storage Bucket gs://${BUCKET_NAME}..."
    gcloud storage buckets create "gs://${BUCKET_NAME}" \
        --location="${GCP_LOCATION}" \
        --uniform-bucket-level-access \
        --project="${GCP_PROJECT_ID}"
else
    echo "✅ Storage bucket gs://${BUCKET_NAME} already exists."
fi

# Upload listing images to GCS
if [ -d "listings" ]; then
    echo "🪣 Uploading listing images to GCS gs://${BUCKET_NAME}/listings/..."
    gcloud storage cp -r ./listings/* "gs://${BUCKET_NAME}/listings/"
fi

# Substitute PROJECT_ID in insert_listings.sql
if [ -f "alloydb-artefacts/insert_listings.sql" ]; then
    echo "✍️ Substituting PROJECT_ID in alloydb-artefacts/insert_listings.sql..."
    sed -i "s/PROJECT_ID_PLACEHOLDER/${GCP_PROJECT_ID}/g" "alloydb-artefacts/insert_listings.sql"
fi

# Generate backend/.env dynamically
ENV_FILE="backend/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "Creating backend/.env configuration..."
    INSTANCE_CONNECTION_NAME="projects/${GCP_PROJECT_ID}/locations/${GCP_LOCATION}/clusters/search-cluster/instances/search-primary"
    
    cat << EOF > "$ENV_FILE"
GCP_PROJECT_ID=${GCP_PROJECT_ID}
GCP_LOCATION=${GCP_LOCATION}
INSTANCE_CONNECTION_NAME=${INSTANCE_CONNECTION_NAME}
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=alloydb-hackathon-password
AGENT_CONTEXT_SET_ID_ALLOYDB=property-agent
ALLOYDB_CLUSTER_ID=search-cluster
ALLOYDB_INSTANCE_ID=search-primary
ALLOWED_GCS_BUCKET=${GCP_PROJECT_ID}-search-demo-images
EOF
    echo "✅ backend/.env generated successfully!"
fi

# 5. Create AlloyDB IAM User for active gcloud user
ACTIVE_USER=$(gcloud config get-value account 2>/dev/null || echo "")
if [ -n "$ACTIVE_USER" ]; then
    echo "👤 Configuring AlloyDB IAM user for ${ACTIVE_USER}..."
    if ! gcloud alloydb users list --cluster=search-cluster --region="${GCP_LOCATION}" --project="${GCP_PROJECT_ID}" --format="value(name)" 2>/dev/null | grep -q "${ACTIVE_USER}"; then
        echo "➕ Creating AlloyDB IAM user ${ACTIVE_USER}..."
        gcloud alloydb users create "${ACTIVE_USER}" \
            --cluster=search-cluster \
            --region="${GCP_LOCATION}" \
            --type=IAM_BASED \
            --db-roles=alloydbsuperuser,alloydbiamuser \
            --project="${GCP_PROJECT_ID}" \
            --quiet
    else
        echo "✅ AlloyDB IAM user ${ACTIVE_USER} already exists."
    fi
fi

echo "✅ Environment initialization completed successfully!"


