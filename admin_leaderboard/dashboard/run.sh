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
echo "  🏰 Disneyland Spanner Admin Leaderboard Starting on :${PORT}  "
echo "================================================================="

# Create and activate local virtualenv if needed
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating local virtualenv in ${VENV_DIR}..."
    python3 -m venv "$VENV_DIR"
    echo "📥 Installing dashboard dependencies..."
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "${SCRIPT_DIR}/requirements.txt"
fi

# Run Streamlit using the virtualenv
echo "🚀 Launching Streamlit UI..."
"$VENV_DIR/bin/streamlit" run app.py --server.port="${PORT}" --server.headless=true

