#!/bin/bash
set -e

# Load environment variables
if [ -f "backend/.env" ]; then
    echo "📄 Loading configuration from backend/.env..."
    set -a
    source backend/.env
    set +a
    # Map GCP_PROJECT_ID to PROJECT_ID for envsubst / tools.yaml
    if [ -n "$GCP_PROJECT_ID" ] && [ -z "$PROJECT_ID" ]; then
        export PROJECT_ID=$GCP_PROJECT_ID
    fi
    # Map GCP_LOCATION to GCP_LOCATION
    if [ -n "$GCP_LOCATION" ] && [ -z "$GCP_LOCATION" ]; then
        export GCP_LOCATION=$GCP_LOCATION
    fi
else
    echo "❌ backend/.env not found. Please run ./init.sh first."
    exit 1
fi

PROJECT_ID=${GCP_PROJECT_ID:-$(gcloud config get-value project)}
REGION=${GCP_LOCATION:-"europe-west1"}
INSTANCE_URI="${INSTANCE_CONNECTION_NAME}"

echo "🔧 Setting up local debug environment..."



# 2. Prepare Configuration using python3 expanding environment variables
echo "🔧 Resolving GDA tools configuration..."
python3 -c "import os, sys; sys.stdout.write(os.path.expandvars(sys.stdin.read()))" < backend/mcp_server/tools.yaml > backend/mcp_server/tools_resolved.yaml

# Prepare credentials with correct permissions for Docker
cp $HOME/.config/gcloud/application_default_credentials.json /tmp/adc.json
chmod 644 /tmp/adc.json

# Cleanup function
cleanup() {
    echo "🧹 Stopping containers..."
    sudo docker stop search-backend search-frontend agent-service toolbox-service 2>/dev/null || true
}
trap cleanup EXIT

# --- PRE-CLEANUP ---
echo "🧹 Cleaning up existing containers..."
sudo docker rm -f search-backend search-frontend agent-service toolbox-service 2>/dev/null || true

# --- BUILD LOCALLY ---
echo "🔨 Building images locally..."
sudo docker build -t local-search-backend backend/
sudo docker build -t local-search-frontend frontend/
sudo docker build -t local-agent-service backend/agent/

# 3. Run Backend Container
echo "📦 Running Backend Container..."
sudo docker run -d --rm \
    --name search-backend \
    --network host \
    -e PORT=8080 \
    -e GCP_PROJECT_ID=$PROJECT_ID \
    -e GCP_LOCATION=$REGION \
    -e AGENT_CONTEXT_SET_ID_ALLOYDB=$AGENT_CONTEXT_SET_ID_ALLOYDB \
    -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/keys.json \
    -v /tmp/adc.json:/tmp/keys.json:ro \
    local-search-backend

echo "   Backend running on localhost:8080"

# 4. Run Toolbox Container (MCP Server)
echo "📦 Running Toolbox Container..."
sudo docker run -d --rm \
    --name toolbox-service \
    --network host \
    -e PORT=8085 \
    -e PROJECT_ID=$PROJECT_ID \
    -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/keys.json \
    -v /tmp/adc.json:/tmp/keys.json:ro \
    -v $(pwd)/backend/mcp_server/tools_resolved.yaml:/secrets/tools.yaml:ro \
    us-central1-docker.pkg.dev/database-toolbox/toolbox/toolbox:latest \
    --tools-file=/secrets/tools.yaml --address=0.0.0.0 --port=8085

echo "   Toolbox running on localhost:8085"

# 5. Run Agent Container
echo "📦 Running Agent Container..."
sudo docker run -d --rm \
    --name agent-service \
    --network host \
    -e PORT=8083 \
    -e GOOGLE_CLOUD_PROJECT=$PROJECT_ID \
    -e GOOGLE_CLOUD_REGION="$REGION" \
    -e GOOGLE_GENAI_USE_VERTEXAI=true \
    -e GOOGLE_CLOUD_LOCATION="global" \
    -e TOOLBOX_URL="http://localhost:8085" \
    -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/keys.json \
    -v /tmp/adc.json:/tmp/keys.json:ro \
    local-agent-service

echo "   Agent running on localhost:8083"

# 6. Run Frontend Container
echo "📦 Running Frontend Container..."
sudo docker run -d --rm \
    --name search-frontend \
    --network host \
    -e PORT=8081 \
    -e BACKEND_URL="http://localhost:8080" \
    -e AGENT_URL="http://localhost:8083" \
    local-search-frontend

echo "   Frontend running on localhost:8081"
echo "🎉 Debug environment ready!"
echo "   Frontend: http://localhost:8081"
echo "   Backend logs: sudo docker logs -f search-backend"
echo "   Agent logs: sudo docker logs -f agent-service"
echo "   Frontend logs: sudo docker logs -f search-frontend"
echo "   Press Ctrl+C to stop."

# Keep script running to maintain trap
while true; do sleep 1; done
