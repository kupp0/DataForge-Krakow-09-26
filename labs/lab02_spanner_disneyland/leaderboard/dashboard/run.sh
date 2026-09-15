#!/usr/bin/env bash
# ==============================================================================
# Run Streamlit Leaderboard Dashboard locally with isolated virtualenv
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${1:-8501}"
VENV_DIR="${SCRIPT_DIR}/.venv"

echo "================================================================="
echo "  🏰 Lab 2: Disneyland Spanner Admin Leaderboard Starting on :${PORT}  "
echo "================================================================="

# Create and activate local virtualenv if needed
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating local virtualenv in ${VENV_DIR}..."
    python3 -m venv "$VENV_DIR"
    echo "📥 Installing dashboard dependencies..."
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "${SCRIPT_DIR}/requirements.txt"
fi

# Set default quota project to admin project if not explicitly set
if [ -z "${GOOGLE_CLOUD_QUOTA_PROJECT:-}" ]; then
    ADMIN_PROJ="${ADMIN_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
    if [ -n "$ADMIN_PROJ" ]; then
        export GOOGLE_CLOUD_QUOTA_PROJECT="$ADMIN_PROJ"
        echo "🔑 Using Quota Project: ${GOOGLE_CLOUD_QUOTA_PROJECT}"
    fi
fi

# Run Streamlit using the virtualenv
echo "🚀 Launching Streamlit UI..."
"$VENV_DIR/bin/streamlit" run app.py --server.port="${PORT}" --server.headless=true

