#!/usr/bin/env bash
# ==============================================================================
# Data Forge: Parallel Cloud Workstation Pre-Warming Coordinator
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECTS_FILE="${SCRIPT_DIR}/projects.txt"
CLUSTER_ID="workstation-cluster"
CONFIG_ID="workstation-config"
WORKSTATION_ID="my-workstation"
DEFAULT_REGION="europe-west3"

if [[ ! -f "$PROJECTS_FILE" ]]; then
  echo "❌ ERROR: projects.txt not found at $PROJECTS_FILE"
  exit 1
fi

echo "================================================================="
echo "🚀 Initiating Parallel Cloud Workstation Pre-Warming..."
echo "================================================================="

PIDS=()
COUNT=0

while IFS= read -r line || [[ -n "$line" ]]; do
  clean_line="$(echo "$line" | cut -d'#' -f1 | tr -d '[:space:]')"
  if [[ -z "$clean_line" ]]; then
    continue
  fi

  IFS=',' read -r PROJ_ID USER_EMAIL REGION <<< "$clean_line"
  REGION="${REGION:-$DEFAULT_REGION}"

  if [[ -z "$PROJ_ID" ]]; then
    continue
  fi

  ((COUNT++))
  echo "  ⚡ [${PROJ_ID}] Triggering async startup (region: ${REGION})..."

  gcloud workstations start "$WORKSTATION_ID" \
    --cluster="$CLUSTER_ID" \
    --config="$CONFIG_ID" \
    --region="$REGION" \
    --project="$PROJ_ID" \
    --async &>/dev/null &
  
  PIDS+=($!)

  # Throttle to max 20 parallel processes
  if (( ${#PIDS[@]} >= 20 )); then
    for pid in "${PIDS[@]}"; do
      wait "$pid" 2>/dev/null || true
    done
    PIDS=()
  fi
done < "$PROJECTS_FILE"

# Wait for remaining processes
for pid in "${PIDS[@]}"; do
  wait "$pid" 2>/dev/null || true
done

echo "================================================================="
echo "✔ Successfully signaled pre-warming for ${COUNT} workstation(s)!"
echo "  Persistent disks and python virtual environments are hydrating."
echo "================================================================="
