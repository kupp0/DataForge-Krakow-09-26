#!/usr/bin/env bash
# ==============================================================================
# Day-0 Verification Script: AlloyDB AI Vectors Lab
# ==============================================================================
set -euo pipefail

echo "🧪 Running Day-0 Verification for AlloyDB AI Vectors..."

if [ -f "user_guide.md" ] || [ -f "../user_guide.md" ] || [ -f "assets/alloydb_studio_menu.png" ]; then
    echo "[PASS] AlloyDB AI lab guide and assets present"
else
    echo "[FAIL] AlloyDB AI assets missing"
    exit 1
fi

if command -v python3 &>/dev/null; then
    echo "[PASS] Python runtime available ($(python3 --version))"
else
    echo "[FAIL] Python3 runtime not found"
    exit 1
fi

echo "[PASS] Day-0 verification completed for AlloyDB AI Vectors"
exit 0
