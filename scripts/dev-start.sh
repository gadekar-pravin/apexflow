#!/bin/bash
set -euo pipefail

PROJECT="apexflow-ai"
ZONE="us-central1-a"
VM="alloydb-omni-dev"

echo "=== ApexFlow Dev Environment — Start ==="

# 1. Start the VM if it's not running
STATUS=$(gcloud compute instances describe "$VM" \
  --project="$PROJECT" --zone="$ZONE" \
  --format='value(status)' 2>/dev/null || echo "NOT_FOUND")

if [ "$STATUS" = "RUNNING" ]; then
  echo "[1/3] VM is already running"
elif [ "$STATUS" = "TERMINATED" ] || [ "$STATUS" = "STOPPED" ]; then
  echo "[1/3] Starting VM..."
  gcloud compute instances start "$VM" --project="$PROJECT" --zone="$ZONE" --quiet
  echo "      Waiting for VM to boot..."
  sleep 10
else
  echo "[1/3] ERROR: VM status is '$STATUS'. Cannot start."
  exit 1
fi

# 2. Wait for AlloyDB Omni to be healthy
echo "[2/3] Waiting for AlloyDB Omni to be healthy..."
for i in $(seq 1 30); do
  HEALTHY=$(gcloud compute ssh "$VM" --zone="$ZONE" --project="$PROJECT" \
    --command="sudo docker compose -f /opt/apexflow/docker-compose.vm.yml ps --format '{{.Health}}' 2>/dev/null" \
    2>/dev/null || echo "")
  if echo "$HEALTHY" | grep -qiw "healthy"; then
    echo "      AlloyDB Omni is healthy!"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "      WARNING: Timed out waiting for AlloyDB Omni. Check VM logs."
    exit 1
  fi
  sleep 5
done

# 3. Open SSH tunnel in the background
echo "[3/3] Opening SSH tunnel (localhost:5432 → VM:5432)..."

# Kill any existing tunnel first
pkill -f "ssh.*${VM}.*5432:localhost:5432" 2>/dev/null || true
sleep 1

gcloud compute ssh "$VM" --zone="$ZONE" --project="$PROJECT" \
  -- -N -L 5432:localhost:5432 -f

echo ""
echo "=== Dev environment is ready ==="
echo "  DB: localhost:5432 (user: apexflow, password: see Secret Manager 'apexflow-db-password')"
echo "  To stop: ./scripts/dev-stop.sh"
echo "================================"
