#!/bin/bash
set -euo pipefail

PROJECT="apexflow-ai"
ZONE="us-central1-a"
VM="alloydb-omni-dev"

echo "=== ApexFlow Dev Environment — Stop ==="

# 1. Close SSH tunnel
echo "[1/2] Closing SSH tunnel..."
pkill -f "ssh.*${VM}.*5432:localhost:5432" 2>/dev/null && echo "      Tunnel closed" || echo "      No tunnel running"

# 2. Stop the VM
STATUS=$(gcloud compute instances describe "$VM" \
  --project="$PROJECT" --zone="$ZONE" \
  --format='value(status)' 2>/dev/null || echo "NOT_FOUND")

if [ "$STATUS" = "RUNNING" ]; then
  echo "[2/2] Stopping VM..."
  gcloud compute instances stop "$VM" --project="$PROJECT" --zone="$ZONE" --quiet
  echo "      VM stopped. Billing paused (disk charges still apply)."
elif [ "$STATUS" = "TERMINATED" ] || [ "$STATUS" = "STOPPED" ]; then
  echo "[2/2] VM is already stopped"
else
  echo "[2/2] VM status is '$STATUS'"
fi

echo ""
echo "=== Dev environment stopped ==="
