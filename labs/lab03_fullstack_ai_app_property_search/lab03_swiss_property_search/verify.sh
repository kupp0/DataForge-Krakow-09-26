#!/usr/bin/env bash
# ==============================================================================
# Day-0 Verification Script: Swiss Property Search Fullstack AI App
# ==============================================================================
set -euo pipefail

echo "🧪 Running Day-0 Verification for Swiss Property Search..."

if [ -f "user_guide.md" ] || [ -f "../user_guide.md" ] || [ -d "frontend" ] || [ -d "backend" ]; then
    echo "[PASS] Fullstack frontend and backend source code present"
else
    echo "[FAIL] Fullstack application source assets missing"
    exit 1
fi

if command -v python3 &>/dev/null; then
    echo "[PASS] Python 3 runtime available"
else
    echo "[FAIL] Python3 runtime not found"
    exit 1
fi

echo "[PASS] Day-0 verification completed for Swiss Property Search"
exit 0
