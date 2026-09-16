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

# ------------------------------------------------------------------
# ADC identity pre-flight.
#
# The dashboard reads 25 participant projects via Application Default
# Credentials, NOT via the gcloud CLI identity -- these are frequently
# different principals. Authenticating as the wrong one does not raise an
# error: every project simply returns nothing, and the board renders a clean
# all-zero leaderboard that looks exactly like a correct pre-event baseline.
# Print the resolved principal so that is obvious before the doors open.
# ------------------------------------------------------------------
echo "🪪 Verifying Application Default Credentials..."
ADC_EMAIL="$("$VENV_DIR/bin/python" - <<'PYEOF' 2>/dev/null || true
import json, urllib.request
import google.auth, google.auth.transport.requests
try:
    creds, _ = google.auth.default()
    creds.refresh(google.auth.transport.requests.Request())
    info = json.load(urllib.request.urlopen(
        "https://oauth2.googleapis.com/tokeninfo?access_token=" + creds.token))
    print(info.get("email") or info.get("sub") or "unknown")
except Exception as e:
    print(f"UNAVAILABLE ({type(e).__name__})")
PYEOF
)"
if [ -z "$ADC_EMAIL" ]; then ADC_EMAIL="UNAVAILABLE"; fi
echo "🪪 ADC principal: ${ADC_EMAIL}"
case "$ADC_EMAIL" in
    UNAVAILABLE*)
        echo "⚠️  Could not resolve ADC. Run: gcloud auth application-default login"
        ;;
    *@google.com)
        ;;
    *)
        echo "⚠️  WARNING: ADC is '${ADC_EMAIL}'."
        echo "⚠️  If this principal lacks access to the participant projects, the board"
        echo "⚠️  will render ALL ZEROS with no error. Re-auth with the correct account:"
        echo "⚠️      gcloud auth application-default login"
        ;;
esac

# Run Streamlit using the virtualenv
echo "🚀 Launching Streamlit UI..."
"$VENV_DIR/bin/streamlit" run app.py --server.port="${PORT}" --server.headless=true

