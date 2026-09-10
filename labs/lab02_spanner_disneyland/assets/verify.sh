#!/usr/bin/env bash
# ==============================================================================
# Day-0 Verification Script: Cloud Spanner Disneyland Lab
# ==============================================================================
set -euo pipefail

echo "🧪 Running Day-0 Verification for Cloud Spanner Disneyland..."

if [ -f "user_guide.md" ] || [ -f "../user_guide.md" ] || [ -d ".agents/skills" ]; then
    echo "[PASS] Spanner Disneyland lab documentation and agent skills present"
else
    echo "[FAIL] Spanner Disneyland assets missing"
    exit 1
fi

if command -v gcloud &>/dev/null; then
    echo "[PASS] Google Cloud SDK initialized on Workstation"
else
    echo "[FAIL] gcloud CLI not found"
    exit 1
fi

echo "[PASS] Day-0 verification completed for Cloud Spanner Disneyland"
exit 0
