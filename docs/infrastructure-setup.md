# ApexFlow Infrastructure Setup Guide

Comprehensive guide to provision all GCP infrastructure for the ApexFlow v2 backend and frontend from scratch. This replicates the production environment originally deployed to `apexflow-ai`.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Variables Reference](#2-variables-reference)
3. [Enable GCP APIs](#3-enable-gcp-apis)
4. [Database VM (AlloyDB Omni on GCE)](#4-database-vm-alloydb-omni-on-gce)
5. [Cloud Scheduler (VM Auto-Stop)](#5-cloud-scheduler-vm-auto-stop)
6. [Artifact Registry](#6-artifact-registry)
7. [Service Accounts and IAM](#7-service-accounts-and-iam)
8. [VPC Connector](#8-vpc-connector)
9. [Firewall Rules](#9-firewall-rules)
10. [Secret Manager](#10-secret-manager)
11. [Database Initialization](#11-database-initialization)
12. [Cloud Build GitHub Connection](#12-cloud-build-github-connection)
13. [Cloud Build Trigger](#13-cloud-build-trigger)
14. [First Deployment](#14-first-deployment)
15. [Verification](#15-verification)
16. [Code Changes for New Project](#16-code-changes-for-new-project)
17. [Local Developer Setup](#17-local-developer-setup)
18. [Ongoing Deployments](#18-ongoing-deployments)
19. [Rollback](#19-rollback)
20. [Cost Management](#20-cost-management)
21. [Architecture Diagram](#21-architecture-diagram)
22. [Firebase Hosting (Frontend)](#22-firebase-hosting-frontend)
23. [Firebase Authentication](#23-firebase-authentication)

---

## 1. Prerequisites

- **gcloud CLI** installed and authenticated (`gcloud auth login`)
- **Google Cloud project** created with billing enabled
- **GitHub repository** containing the ApexFlow codebase
- **Domain/frontend URL** for CORS configuration (e.g., `https://apexflow.web.app`)
- **Python 3.12+** and **uv** for local development

---

## 2. Variables Reference

Set these variables at the start of your session. Every command in this guide uses them.

```bash
# === EDIT THESE FOR YOUR ENVIRONMENT ===
export PROJECT_ID="apexflow-ai"               # Your GCP project ID
export REGION="us-central1"                    # GCP region
export ZONE="${REGION}-a"                      # GCE zone
export VM_NAME="alloydb-omni-dev"             # Database VM name
export VM_MACHINE_TYPE="n2-standard-4"        # VM size (4 vCPU, 16 GB RAM)
export VM_DISK_SIZE="50"                      # Boot disk GB
export DB_USER="apexflow"                     # PostgreSQL username
export DB_NAME="apexflow"                     # PostgreSQL database name
export GITHUB_OWNER="gadekar-pravin"          # GitHub username or org
export GITHUB_REPO="apexflow"                 # GitHub repository name
export FRONTEND_ORIGIN="https://apexflow-console.web.app"  # Firebase Hosting URL
export CLOUD_RUN_SERVICE="apexflow-api"       # Cloud Run service name
export AR_REPO="apexflow-api"                 # Artifact Registry repo name
export VPC_CONNECTOR="apexflow-vpc-connector" # VPC connector name
export VPC_CONNECTOR_RANGE="10.8.0.0/28"      # VPC connector CIDR (must not overlap existing subnets)

# === DERIVED (don't edit) ===
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/api"
export API_SA="${CLOUD_RUN_SERVICE}@${PROJECT_ID}.iam.gserviceaccount.com"
export CI_SA="cloudbuild-ci@${PROJECT_ID}.iam.gserviceaccount.com"
export SCHEDULER_SA="vm-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
```

---

## 3. Enable GCP APIs

```bash
gcloud services enable \
  compute.googleapis.com \
  run.googleapis.com \
  vpcaccess.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com \
  identitytoolkit.googleapis.com \
  iap.googleapis.com \
  --project=$PROJECT_ID
```

---

## 4. Database VM (AlloyDB Omni on GCE)

AlloyDB Omni runs as a Docker container on a GCE VM. This provides managed-AlloyDB compatibility (pgvector + ScaNN indexes) at GCE pricing.

### 4a. Create the VM

```bash
gcloud compute instances create $VM_NAME \
  --zone=$ZONE \
  --machine-type=$VM_MACHINE_TYPE \
  --boot-disk-size=${VM_DISK_SIZE}GB \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --network=default \
  --tags=alloydb \
  --metadata=startup-script='#!/bin/bash
    apt-get update && apt-get install -y docker.io docker-compose-v2
    systemctl enable docker && systemctl start docker
  ' \
  --project=$PROJECT_ID
```

Wait ~2 minutes for the VM to boot and install Docker.

### 4b. Create the directory structure on the VM

```bash
gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command="
  sudo mkdir -p /opt/apexflow/scripts
"
```

### 4c. Copy the init-db.sql schema to the VM

```bash
gcloud compute scp scripts/init-db.sql \
  $VM_NAME:/tmp/init-db.sql \
  --zone=$ZONE --project=$PROJECT_ID

gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command="
  sudo mv /tmp/init-db.sql /opt/apexflow/scripts/init-db.sql
"
```

### 4d. Create docker-compose.vm.yml on the VM

```bash
gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command="
sudo tee /opt/apexflow/docker-compose.vm.yml > /dev/null << 'COMPOSE_EOF'
version: '3.8'
services:
  alloydb-omni:
    image: google/alloydbomni:15.12.0
    restart: always
    ports:
      - \"5432:5432\"
    environment:
      POSTGRES_USER: apexflow
      POSTGRES_PASSWORD: apexflow
      POSTGRES_DB: apexflow
    volumes:
      - alloydb_data:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/01-schema.sql
    shm_size: '512mb'
    ulimits:
      nice:
        soft: -20
        hard: -20
      memlock:
        soft: -1
        hard: -1
    healthcheck:
      test: [\"CMD-SHELL\", \"pg_isready -U apexflow -d apexflow\"]
      interval: 5s
      timeout: 3s
      retries: 10
    logging:
      driver: \"json-file\"
      options:
        max-size: \"10m\"
        max-file: \"3\"

volumes:
  alloydb_data:
COMPOSE_EOF
"
```

### 4e. Start AlloyDB Omni

```bash
gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command="
  cd /opt/apexflow && sudo docker compose -f docker-compose.vm.yml up -d
"
```

Wait ~30 seconds, then verify:

```bash
gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command="
  sudo docker compose -f /opt/apexflow/docker-compose.vm.yml ps --format '{{.Health}}'
"
# Expected: healthy
```

### 4f. Get the VM internal IP

```bash
VM_INTERNAL_IP=$(gcloud compute instances describe $VM_NAME \
  --zone=$ZONE \
  --format='value(networkInterfaces[0].networkIP)' \
  --project=$PROJECT_ID)

echo "VM Internal IP: $VM_INTERNAL_IP"
```

**Save this IP** — it's needed for Cloud Run to connect to the database.

### 4g. Set a strong production password

The docker-compose uses `apexflow` as the initial password. Change it immediately:

```bash
# Generate a strong password
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "Generated DB password: $DB_PASSWORD"

# Find the container name
CONTAINER=$(gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID \
  --command="sudo docker ps --format '{{.Names}}'" 2>/dev/null)

# Change the password
gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID \
  --command="sudo docker exec $CONTAINER psql -U $DB_USER -d $DB_NAME -c \"ALTER USER $DB_USER WITH PASSWORD '$DB_PASSWORD';\""
# Expected output: ALTER ROLE
```

> **Important:** Note the docker-compose.vm.yml still has the initial password. This is only used for the initial `POSTGRES_PASSWORD` during first container creation. After changing via ALTER USER, the new password is what's active. If you ever recreate the container from scratch (destroying the volume), you'd need to update docker-compose.vm.yml too.

---

## 5. Cloud Scheduler (Nightly Auto-Stop)

Automatically stops the database VM and disables the Cloud Run service nightly at 11 PM IST to save costs during development.

### 5a. Create the scheduler service account

```bash
gcloud iam service-accounts create vm-scheduler \
  --display-name="VM Auto-Stop Scheduler" \
  --project=$PROJECT_ID

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SCHEDULER_SA" \
  --role="roles/compute.instanceAdmin.v1"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SCHEDULER_SA" \
  --role="roles/run.developer"
```

### 5b. Create the VM auto-stop job

```bash
gcloud scheduler jobs create http vm-auto-stop \
  --location=$REGION \
  --schedule="0 23 * * *" \
  --time-zone="Asia/Kolkata" \
  --description="Auto-stop $VM_NAME VM every night at 11 PM IST" \
  --uri="https://compute.googleapis.com/compute/v1/projects/$PROJECT_ID/zones/$ZONE/instances/$VM_NAME/stop" \
  --http-method=POST \
  --oauth-service-account-email=$SCHEDULER_SA \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --attempt-deadline=180s \
  --project=$PROJECT_ID
```

### 5c. Create the Cloud Run auto-stop job

Switches Cloud Run ingress to `internal-only`, blocking all external traffic. The service stays deployed but unreachable. Uses `X-HTTP-Method-Override: PATCH` because Cloud Scheduler doesn't support PATCH directly.

```bash
gcloud scheduler jobs create http cloudrun-auto-stop \
  --location=$REGION \
  --schedule="0 23 * * *" \
  --time-zone="Asia/Kolkata" \
  --description="Auto-disable Cloud Run $CLOUD_RUN_SERVICE every night at 11 PM IST (set ingress to internal-only)" \
  --uri="https://run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/services/$CLOUD_RUN_SERVICE?updateMask=ingress" \
  --http-method=post \
  --headers="Content-Type=application/json,X-HTTP-Method-Override=PATCH" \
  --message-body='{"ingress": "INGRESS_TRAFFIC_INTERNAL_ONLY"}' \
  --oauth-service-account-email=$SCHEDULER_SA \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --attempt-deadline=180s \
  --project=$PROJECT_ID
```

To manually re-enable external traffic:

```bash
gcloud run services update $CLOUD_RUN_SERVICE \
  --ingress=all \
  --region=$REGION \
  --project=$PROJECT_ID
```

---

## 6. Artifact Registry

Docker image repository for the API container.

```bash
gcloud artifacts repositories create $AR_REPO \
  --repository-format=docker \
  --location=$REGION \
  --description="ApexFlow API container images" \
  --project=$PROJECT_ID
```

---

## 7. Service Accounts and IAM

### 7a. Cloud Run API service account

This is the runtime identity for the Cloud Run service.

```bash
gcloud iam service-accounts create $CLOUD_RUN_SERVICE \
  --display-name="ApexFlow API Service Account" \
  --project=$PROJECT_ID
```

Grant Vertex AI access (for Gemini LLM calls via ADC):

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$API_SA" \
  --role="roles/aiplatform.user"
```

> **Note:** Secret Manager access for this SA is granted at the secret level (Step 10), not at the project level.

### 7b. Cloud Build CI service account

This is used by the Cloud Build trigger for CI/CD.

```bash
gcloud iam service-accounts create cloudbuild-ci \
  --display-name="Cloud Build CI" \
  --project=$PROJECT_ID
```

Grant the roles needed for the CI/CD pipeline:

```bash
for role in \
  roles/cloudbuild.builds.builder \
  roles/run.admin \
  roles/iam.serviceAccountUser \
  roles/artifactregistry.writer \
  roles/logging.logWriter \
  roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$CI_SA" \
    --role="$role"
done
```

### 7c. IAM role summary

| Service Account | Purpose | Project-Level Roles |
|---|---|---|
| `apexflow-api@` | Cloud Run runtime | `roles/aiplatform.user` |
| `cloudbuild-ci@` | CI/CD pipeline | `roles/cloudbuild.builds.builder`, `roles/run.admin`, `roles/iam.serviceAccountUser`, `roles/artifactregistry.writer`, `roles/logging.logWriter`, `roles/secretmanager.secretAccessor` |
| `vm-scheduler@` | Nightly VM + Cloud Run auto-stop | `roles/compute.instanceAdmin.v1`, `roles/run.developer` |

---

## 8. VPC Connector

Allows Cloud Run to reach the GCE VM's private IP over the VPC.

```bash
gcloud compute networks vpc-access connectors create $VPC_CONNECTOR \
  --region=$REGION \
  --network=default \
  --range=$VPC_CONNECTOR_RANGE \
  --min-instances=2 \
  --max-instances=3 \
  --machine-type=e2-micro \
  --project=$PROJECT_ID
```

This takes 2-3 minutes to provision.

---

## 9. Firewall Rules

The default VPC `default-allow-internal` rule covers `10.128.0.0/9`, which includes the GCE VM. However, the VPC connector uses a separate CIDR (`10.8.0.0/28`) that falls outside that range. A dedicated rule is needed:

```bash
gcloud compute firewall-rules create allow-vpc-connector-to-alloydb \
  --network=default \
  --allow=tcp:5432 \
  --source-ranges=$VPC_CONNECTOR_RANGE \
  --description="Allow VPC connector to reach AlloyDB on port 5432" \
  --project=$PROJECT_ID
```

### Firewall rules summary

| Rule | Source | Allowed | Purpose |
|---|---|---|---|
| `default-allow-internal` | `10.128.0.0/9` | all TCP/UDP/ICMP | Intra-VPC (covers SSH tunnel to VM) |
| `default-allow-ssh` | `0.0.0.0/0` | TCP 22 | SSH access to VM |
| `allow-vpc-connector-to-alloydb` | `10.8.0.0/28` | TCP 5432 | Cloud Run → AlloyDB via VPC connector |

---

## 10. Secret Manager

### 10a. Create the database password secret

```bash
echo -n "$DB_PASSWORD" | gcloud secrets create apexflow-db-password \
  --data-file=- --project=$PROJECT_ID
```

### 10b. Grant secret-level access

Both the Cloud Run SA (runtime) and Cloud Build CI SA (deployment) need access:

```bash
for sa in $API_SA $CI_SA; do
  gcloud secrets add-iam-policy-binding apexflow-db-password \
    --member="serviceAccount:$sa" \
    --role="roles/secretmanager.secretAccessor" \
    --project=$PROJECT_ID
done
```

### Why no Gemini API key?

On Cloud Run, `K_SERVICE` is set automatically, which triggers Vertex AI mode in `core/gemini_client.py`. The client uses Application Default Credentials (ADC) tied to the Cloud Run service account (`apexflow-api@`), which has `roles/aiplatform.user`. No API key is needed.

For **local development**, set `GEMINI_API_KEY` in your `.env` file.

---

## 11. Database Initialization

### 11a. Start the SSH tunnel

```bash
./scripts/dev-start.sh
```

Or manually:

```bash
# Start VM if stopped
gcloud compute instances start $VM_NAME --zone=$ZONE --project=$PROJECT_ID

# Open SSH tunnel
gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID \
  -- -N -L 5432:localhost:5432 -f
```

### 11b. Run Alembic migrations

The schema is bootstrapped by `init-db.sql` (mounted via docker-compose), and Alembic manages incremental migrations (5 migrations: 001-005).

```bash
DB_HOST=localhost DB_USER=$DB_USER DB_PASSWORD=$DB_PASSWORD \
  alembic upgrade head
```

Verify:

```bash
DB_HOST=localhost DB_USER=$DB_USER DB_PASSWORD=$DB_PASSWORD \
  alembic current
# Expected: 005 (head)
```

### Migration files

| Migration | Description |
|---|---|
| `001_initial_schema.py` | Base schema (13 tables) |
| `002_rag_versioning_columns.py` | RAG document versioning columns |
| `003_add_chunk_method_column.py` | Chunking method tracking |
| `004_add_memory_embedding_model.py` | Memory embedding model column |
| `005_sandbox_security_logs.py` | Sandbox security log JSONB details |

---

## 12. Cloud Build GitHub Connection

Cloud Build needs a GitHub connection to trigger builds on tag pushes. This is a **one-time interactive setup** done through the Google Cloud Console.

### 12a. Create the connection (Console)

1. Go to **Cloud Build > Repositories (2nd gen)** in the [Cloud Console](https://console.cloud.google.com/cloud-build/repositories)
2. Select region: `us-central1`
3. Click **Create Host Connection**
4. Choose **GitHub** as the provider
5. Name the connection (e.g., `apexflow-github`)
6. Follow the OAuth flow to authorize Google Cloud Build on your GitHub account
7. Install the Cloud Build GitHub App on your repository

### 12b. Link the repository

After the connection is created:

1. Click **Link Repository**
2. Select the connection you just created
3. Choose the `apexflow` repository
4. Give it a name (e.g., `apexflow-repo`)

### 12c. Verify

```bash
gcloud builds connections list --region=$REGION --project=$PROJECT_ID
# Expected: apexflow-github  COMPLETE  Enabled

gcloud builds connections describe apexflow-github \
  --region=$REGION --project=$PROJECT_ID
# Should show githubConfig with your username
```

---

## 13. Cloud Build Trigger

Create a trigger that fires on version tag pushes (`v*`).

```bash
# Get the full repository resource name
REPO_RESOURCE=$(gcloud builds repositories list \
  --connection=apexflow-github \
  --region=$REGION \
  --project=$PROJECT_ID \
  --format='value(name)')

gcloud builds triggers create github \
  --name=apexflow-ci \
  --repository=$REPO_RESOURCE \
  --tag-pattern='^v.*$' \
  --build-config=cloudbuild.yaml \
  --service-account=projects/$PROJECT_ID/serviceAccounts/$CI_SA \
  --region=$REGION \
  --project=$PROJECT_ID
```

### Add the AlloyDB host substitution

The trigger needs `_ALLOYDB_HOST` set to the VM's internal IP. Update via the REST API:

```bash
TRIGGER_ID=$(gcloud builds triggers list --region=$REGION --project=$PROJECT_ID \
  --filter="name=apexflow-ci" --format='value(id)')

ACCESS_TOKEN=$(gcloud auth print-access-token)

curl -s -X PATCH \
  "https://cloudbuild.googleapis.com/v1/projects/$PROJECT_ID/locations/$REGION/triggers/$TRIGGER_ID?updateMask=substitutions" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"substitutions\": {
      \"_ALLOYDB_HOST\": \"$VM_INTERNAL_IP\"
    }
  }"
```

---

## 14. First Deployment

For the very first deployment, submit a manual build. This runs the full pipeline: lint, typecheck, test, Docker build, push, and deploy.

```bash
SHORT_SHA=$(git rev-parse --short HEAD)

gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions="_ALLOYDB_HOST=$VM_INTERNAL_IP,SHORT_SHA=$SHORT_SHA" \
  --project=$PROJECT_ID
```

> **Note:** The `SHORT_SHA` substitution is auto-populated by Cloud Build triggers but must be passed manually for `gcloud builds submit`.

If the full pipeline is slow and you just need to deploy (e.g., the image already exists), deploy directly:

```bash
gcloud run deploy $CLOUD_RUN_SERVICE \
  --image=$IMAGE:$SHORT_SHA \
  --region=$REGION \
  --platform=managed \
  --allow-unauthenticated \
  --service-account=$API_SA \
  --vpc-connector=$VPC_CONNECTOR \
  --vpc-egress=private-ranges-only \
  --set-secrets=ALLOYDB_PASSWORD=apexflow-db-password:latest \
  --set-env-vars=ALLOYDB_HOST=$VM_INTERNAL_IP,ALLOYDB_DB=$DB_NAME,ALLOYDB_USER=$DB_USER,LOG_LEVEL=INFO,CORS_ORIGINS=$FRONTEND_ORIGIN,ALLOWED_EMAILS=pbgadekar@gmail.com,pravin.gaadekar@gmail.com \
  --memory=2Gi \
  --cpu=2 \
  --concurrency=80 \
  --min-instances=0 \
  --max-instances=1 \
  --timeout=300 \
  --project=$PROJECT_ID
```

---

## 15. Verification

```bash
SERVICE_URL=$(gcloud run services describe $CLOUD_RUN_SERVICE \
  --region=$REGION --format='value(status.url)' --project=$PROJECT_ID)

echo "Service URL: $SERVICE_URL"

# 1. Liveness (app is running)
curl -s $SERVICE_URL/liveness
# Expected: {"status":"alive"}

# 2. Readiness (DB connectivity confirmed)
curl -s $SERVICE_URL/readiness
# Expected: {"status":"ready","cached":false}

# 3. OpenAPI docs
curl -s -o /dev/null -w "HTTP %{http_code}" $SERVICE_URL/docs
# Expected: HTTP 200

# 4. Auth enforcement (K_SERVICE blocks AUTH_DISABLED)
curl -s $SERVICE_URL/api/runs
# Expected: {"detail":"Missing or invalid Authorization header"}

# 5. CORS headers
curl -s -I -H "Origin: $FRONTEND_ORIGIN" $SERVICE_URL/liveness 2>&1 | grep access-control
# Expected: access-control-allow-origin: <your frontend origin>

# 6. Endpoint count
curl -s $SERVICE_URL/openapi.json | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print(f'{len(d[\"paths\"])} endpoints')"
# Expected: 49 endpoints
```

---

## 16. Code Changes for New Project

When deploying to a different GCP project, update these files:

### `cloudbuild.yaml`

Update the hardcoded project ID and region in the `_IMAGE` and `_SERVICE_ACCOUNT` substitutions:

```yaml
substitutions:
  _REGION: us-central1  # change if using a different region
  _IMAGE: us-central1-docker.pkg.dev/YOUR_PROJECT_ID/apexflow-api/api
  _SERVICE_ACCOUNT: apexflow-api@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

> **Why hardcoded?** Cloud Build does not support nested substitution resolution (e.g., `${_REGION}-docker.pkg.dev/${PROJECT_ID}/...` fails because `PROJECT_ID` is not expanded within another substitution definition). Hardcoding avoids this limitation.

### `core/gemini_client.py`

Update the default project:

```python
VERTEX_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "YOUR_PROJECT_ID")
```

Or set the `GOOGLE_CLOUD_PROJECT` env var on Cloud Run.

### `CLAUDE.md`

Update GCP project references.

### `.env.example`

Update the `GCP_PROJECT_ID` default.

---

## 17. Local Developer Setup

### 17a. Clone and install

```bash
git clone git@github.com:$GITHUB_OWNER/$GITHUB_REPO.git
cd $GITHUB_REPO

uv venv .venv && source .venv/bin/activate
uv sync --extra dev
```

### 17b. Configure `.env`

```bash
cp .env.example .env
```

Edit `.env`:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=apexflow
DB_USER=apexflow
DB_PASSWORD=<password from Secret Manager: apexflow-db-password>
DB_SSLMODE=disable

GCP_PROJECT_ID=<your-project-id>
GEMINI_API_KEY=<your-gemini-api-key>
```

To retrieve the DB password:

```bash
gcloud secrets versions access latest --secret=apexflow-db-password --project=$PROJECT_ID
```

### 17c. Connect to database

```bash
./scripts/dev-start.sh    # starts VM + SSH tunnel to localhost:5432
./scripts/dev-stop.sh     # closes tunnel + stops VM
```

### 17d. Run the API server

```bash
AUTH_DISABLED=1 uvicorn api:app --reload
```

### 17e. Run tests

```bash
pytest tests/ -v                  # full suite
pytest tests/unit/ -v             # unit tests only (no DB needed)
pytest tests/integration/ -v      # integration tests (requires AlloyDB)
```

---

## 18. Ongoing Deployments

After the trigger is set up, deployments are automated:

```bash
git tag v2.1.0
git push origin v2.1.0
```

This triggers: lint → typecheck → unit tests + integration tests (in parallel) → Docker build → push to Artifact Registry → deploy to Cloud Run → post-deploy smoke test.

The **smoke test** (Step 10) automatically verifies the deployed service after each deploy:
- `GET /liveness` → 200 (process alive)
- `GET /readiness` → 200 (DB connected via VPC connector → AlloyDB)
- `GET /api/runs` → 401 (Firebase auth enforced in production)

It waits up to 60 seconds for the new revision to become ready before checking. If the GCE VM is stopped (e.g., nightly auto-stop), the readiness check will fail — catching real connectivity issues.

Monitor builds:

```bash
gcloud builds list --region=$REGION --limit=5 --project=$PROJECT_ID
gcloud builds log <BUILD_ID> --project=$PROJECT_ID
```

---

## 19. Rollback

```bash
# List revisions
gcloud run revisions list --service=$CLOUD_RUN_SERVICE --region=$REGION --project=$PROJECT_ID

# Route 100% traffic to a previous revision
gcloud run services update-traffic $CLOUD_RUN_SERVICE \
  --region=$REGION \
  --to-revisions=PREVIOUS_REVISION_NAME=100 \
  --project=$PROJECT_ID
```

---

## 20. Cost Management

### Cost-saving measures already in place

- **Cloud Scheduler** auto-stops the DB VM and disables Cloud Run (ingress → internal-only) at 11 PM IST nightly (saves ~$100/mo in compute when idle)
- **VPC connector** uses `e2-micro` instances (cheapest option)
- **Cloud Run** scales to zero when idle; nightly ingress lockdown prevents any off-hours traffic from spinning up instances
- **Cloud Build** uses `CLOUD_LOGGING_ONLY` (no GCS log storage costs)

### Monthly cost estimate (us-central1)

| Resource | Spec | Est. Monthly Cost |
|---|---|---|
| GCE VM (`n2-standard-4`) | 4 vCPU, 16 GB, 50 GB disk, ~14 hrs/day | ~$95 |
| Cloud Run | 2 CPU, 2 Gi, min 0 / max 1 instance | ~$5-20 (usage-dependent) |
| VPC Connector | 2x `e2-micro` always-on | ~$14 |
| Artifact Registry | Image storage | ~$1-3 |
| Secret Manager | 1 secret, low access | ~$0.06 |
| Cloud Build | E2_HIGHCPU_8, per-build | ~$0.50/build |
| Cloud Scheduler | 1 job | Free tier |

**Total estimate:** ~$115-135/month for development workloads.

### Further cost reduction options

- Use a smaller VM (`e2-medium`) if memory permits
- Stop the VM manually during weekends (`./scripts/dev-stop.sh`)
- Use preemptible/spot VMs for non-production (add `--provisioning-model=SPOT`)

---

## 21. Architecture Diagram

```
  ┌─────────────────────────────┐
  │       User Browser          │
  └──────────────┬──────────────┘
                 │
                 ▼
  ┌─────────────────────────────┐
  │    Firebase Hosting         │
  │  apexflow-console.web.app   │
  │  Serves: frontend/dist      │
  │  Rewrites: /api/** →        │
  │    Cloud Run (same-origin)  │
  └──────────────┬──────────────┘
                 │ rewrite
                 ▼
  ┌─────────────────────────────┐
  │       GitHub Repository     │
  │  (tag push: v* triggers CI) │
  └──────────────┬──────────────┘
                 │
                 ▼
  ┌─────────────────────────────┐
  │        Cloud Build          │
  │  lint → typecheck → test →  │
  │  docker build → push → deploy│
  │  SA: cloudbuild-ci@          │
  └──────────────┬──────────────┘
                 │
            ┌────┬────┐
            ▼         ▼
  ┌──────────────┐  ┌──────────────────┐
  │ Artifact     │  │    Cloud Run      │
  │ Registry     │  │  apexflow-api     │◄── Firebase Hosting rewrites
  │ (images)     │  │  SA: apexflow-api@ │
  └──────────────┘  │  Port: 8080       │
                    │  Min: 0 / Max: 1   │
                    └────────┬─────────┘
                             │
                             │ VPC Connector
                             │ (10.8.0.0/28)
                             │
                             ▼
              ┌─────────────────────────────┐
              │    GCE VM: alloydb-omni-dev  │
              │    n2-standard-4             │
              │    Internal IP: 10.128.0.x   │
              │  ┌───────────────────────┐  │
              │  │  AlloyDB Omni 15.12.0 │  │
              │  │  PostgreSQL + pgvector │  │
              │  │  + ScaNN indexes      │  │
              │  │  Port: 5432           │  │
              │  └───────────────────────┘  │
              └─────────────────────────────┘
                             ▲
                             │ SSH Tunnel
                             │ (localhost:5432)
              ┌─────────────────────────────┐
              │    Developer Laptop          │
              │  ./scripts/dev-start.sh      │
              │  AUTH_DISABLED=1 uvicorn ...  │
              └─────────────────────────────┘


  Secret Manager                    Cloud Scheduler (11 PM IST)
  ┌──────────────────┐              ┌─────────────────────────┐
  │ apexflow-db-     │              │ vm-auto-stop            │
  │ password         │              │   stops GCE VM          │
  │ (mounted in      │              │ cloudrun-auto-stop      │
  │  Cloud Run)      │              │   ingress → internal    │
  └──────────────────┘              │ SA: vm-scheduler@       │
                                    └─────────────────────────┘
```

### Environment detection flow

```
Application starts
  │
  ├─ DATABASE_URL set? ──────────────→ Use explicit URL
  │
  ├─ K_SERVICE set? (Cloud Run) ────→ Use ALLOYDB_* env vars
  │                                    Use Vertex AI ADC for Gemini
  │                                    Auth enforced (Firebase JWT)
  │
  └─ Neither (local dev) ──────────→ Use DB_* env vars (localhost)
                                      Use GEMINI_API_KEY
                                      AUTH_DISABLED=1 allowed
```

---

## 22. Firebase Hosting (Frontend)

The React frontend is deployed via Firebase Hosting in the **same** `apexflow-ai` project as the Cloud Run backend. This is required because Firebase Hosting rewrites to Cloud Run only work within the same GCP project.

### 22a. Enable Firebase on the GCP project (one-time)

```bash
firebase projects:addfirebase $PROJECT_ID
```

### 22b. Create a hosting site

```bash
firebase hosting:sites:create apexflow-console --project $PROJECT_ID
```

This creates the site at `https://apexflow-console.web.app`.

### 22c. Configuration files

Two files at the repo root configure Firebase Hosting:

**`.firebaserc`** — project and deploy target mapping:

```json
{
  "projects": {
    "default": "apexflow-ai"
  },
  "targets": {
    "apexflow-ai": {
      "hosting": {
        "console": ["apexflow-console"]
      }
    }
  }
}
```

**`firebase.json`** — hosting config with Cloud Run rewrites:

```json
{
  "hosting": {
    "target": "console",
    "public": "frontend/dist",
    "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
    "rewrites": [
      {
        "source": "/api/**",
        "run": { "serviceId": "apexflow-api", "region": "us-central1" }
      },
      {
        "source": "/liveness",
        "run": { "serviceId": "apexflow-api", "region": "us-central1" }
      },
      {
        "source": "/readiness",
        "run": { "serviceId": "apexflow-api", "region": "us-central1" }
      },
      {
        "source": "**",
        "destination": "/index.html"
      }
    ],
    "headers": [
      {
        "source": "/assets/**",
        "headers": [{ "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }]
      },
      {
        "source": "**/*.html",
        "headers": [
          { "key": "Cache-Control", "value": "no-cache" },
          { "key": "Cross-Origin-Opener-Policy", "value": "same-origin-allow-popups" }
        ]
      }
    ]
  }
}
```

### 22d. Deploy

```bash
# Build frontend and deploy
cd frontend && npm run build && cd ..
firebase deploy --only hosting:console
```

### 22e. Verify

```bash
# Frontend serves index.html
curl -s -o /dev/null -w "%{http_code}" https://apexflow-console.web.app/
# Expected: 200

# API rewrites proxy to Cloud Run
curl -s https://apexflow-console.web.app/liveness
# Expected: {"status":"alive"}

# SPA routing works (returns index.html for any path)
curl -s -o /dev/null -w "%{http_code}" https://apexflow-console.web.app/documents
# Expected: 200
```

### Why same project?

Firebase Hosting rewrites to Cloud Run [require the service to be in the same Firebase project](https://firebase.google.com/docs/hosting/cloud-run). Since the backend runs in `apexflow-ai`, the hosting site must also be in `apexflow-ai`. This means API calls from the browser go through Firebase Hosting's CDN edge to Cloud Run — same-origin from the browser's perspective, so no CORS configuration is needed for the frontend.

### CORS note

The Cloud Run service's `CORS_ORIGINS` env var does **not** need to include the Firebase Hosting URL when using rewrites (requests are same-origin). CORS is only relevant for direct cross-origin API calls (e.g., from `localhost:5173` during local dev).

---

## 23. Firebase Authentication

Firebase Authentication provides Google sign-in for the frontend. The backend validates Firebase JWTs via the Admin SDK.

### 23a. Initialize Identity Platform

Identity Platform is the GCP service backing Firebase Auth. Initialize it via the REST API:

```bash
curl -s -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "x-goog-user-project: $PROJECT_ID" \
  -H "Content-Type: application/json" \
  -d '{}' \
  "https://identitytoolkit.googleapis.com/v2/projects/$PROJECT_ID/identityPlatform:initializeAuth"
```

### 23b. Enable Google sign-in provider (Console)

The Google sign-in provider requires an OAuth consent screen and Web OAuth client, which must be created through the Firebase Console for personal GCP projects (non-organization).

1. Go to https://console.firebase.google.com/project/$PROJECT_ID/authentication/providers
2. Click **"Get Started"** if prompted
3. Click **Google** > Toggle **Enable** > Set **Project support email** > **Save**

This auto-creates the OAuth consent screen and Web OAuth client.

### 23c. Configure authorized domains

1. Go to https://console.firebase.google.com/project/$PROJECT_ID/authentication/settings
2. Under **Authorized domains**, verify these are listed:
   - `localhost` (local dev)
   - `apexflow-console.web.app` (Firebase Hosting)
   - `apexflow-ai.firebaseapp.com` (authDomain)

### 23d. Verify via CLI

```bash
# Check Google sign-in is enabled
curl -s \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "x-goog-user-project: $PROJECT_ID" \
  "https://identitytoolkit.googleapis.com/admin/v2/projects/$PROJECT_ID/defaultSupportedIdpConfigs/google.com" \
  | python3 -m json.tool
# Expected: {"enabled": true, "clientId": "...", "clientSecret": "..."}

# Check authorized domains
curl -s \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "x-goog-user-project: $PROJECT_ID" \
  "https://identitytoolkit.googleapis.com/admin/v2/projects/$PROJECT_ID/config" \
  | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('authorizedDomains',[]), indent=2))"
# Expected: ["apexflow-ai.firebaseapp.com", "apexflow-ai.web.app", "apexflow-console.web.app", "localhost"]
```

### 23e. Frontend configuration

Firebase config values are set in `frontend/.env.production`. These are public (embedded in the built JS bundle — security is in Firebase Security Rules and backend JWT verification):

```env
VITE_FIREBASE_API_KEY=AIzaSy...
VITE_FIREBASE_AUTH_DOMAIN=apexflow-ai.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=apexflow-ai
VITE_FIREBASE_STORAGE_BUCKET=apexflow-ai.firebasestorage.app
VITE_FIREBASE_MESSAGING_SENDER_ID=807506425655
VITE_FIREBASE_APP_ID=1:807506425655:web:...
```

When these are unset (local dev without `.env.production`), auth is bypassed entirely.

### 23f. COOP headers

`Cross-Origin-Opener-Policy: same-origin-allow-popups` must be set on HTML responses to allow Firebase's `signInWithPopup` to poll `window.closed`. Configured in:
- `frontend/vite.config.ts` — `server.headers` (dev)
- `firebase.json` — `headers` on `**/*.html` (production)

### 23g. Backend auth middleware

The backend (`core/auth.py`) verifies Firebase JWTs. Key behaviors:
- Accepts tokens from `Authorization: Bearer <token>` header OR `?token=` query param (for SSE/EventSource)
- Skip paths: `/liveness`, `/readiness`, `/docs`, `/openapi.json`
- All other endpoints (including `/api/events` SSE) require auth
- `AUTH_DISABLED=1` bypasses auth locally; fails startup if set on Cloud Run
- `ALLOWED_EMAILS` env var (comma-separated) restricts access to listed emails (returns 403 Forbidden); when unset, all authenticated users are allowed

### 23h. Managing the email allowlist

The `ALLOWED_EMAILS` env var controls which Google accounts can use the application. Comparison is case-insensitive. Changes take effect on the next Cloud Run cold start (or force a new revision with `gcloud run deploy`).

**Add or update authorized users:**

```bash
gcloud run services update apexflow-api \
  --region=$REGION \
  --update-env-vars="ALLOWED_EMAILS=pbgadekar@gmail.com,pravin.gaadekar@gmail.com" \
  --project=$PROJECT_ID
```

**Add a user to the existing list** — include all current emails plus the new one:

```bash
gcloud run services update apexflow-api \
  --region=$REGION \
  --update-env-vars="ALLOWED_EMAILS=pbgadekar@gmail.com,pravin.gaadekar@gmail.com,newuser@gmail.com" \
  --project=$PROJECT_ID
```

**Remove a user** — rewrite the list without their email:

```bash
gcloud run services update apexflow-api \
  --region=$REGION \
  --update-env-vars="ALLOWED_EMAILS=pbgadekar@gmail.com" \
  --project=$PROJECT_ID
```

**Remove the allowlist entirely (open access):**

```bash
gcloud run services update apexflow-api \
  --region=$REGION \
  --remove-env-vars=ALLOWED_EMAILS \
  --project=$PROJECT_ID
```

**Verify current setting:**

```bash
gcloud run services describe apexflow-api \
  --region=$REGION \
  --format='value(spec.template.spec.containers[0].env)' \
  --project=$PROJECT_ID | tr ',' '\n' | grep ALLOWED
```

---

## Appendix: Complete Resource Inventory

| Resource Type | Name | Key Config |
|---|---|---|
| GCP Project | `apexflow-ai` | Billing enabled |
| GCE VM | `alloydb-omni-dev` | `n2-standard-4`, `us-central1-a`, 50 GB disk, tag: `alloydb` |
| Docker (on VM) | AlloyDB Omni | `google/alloydbomni:15.12.0`, port 5432 |
| Artifact Registry | `apexflow-api` | Docker, `us-central1` |
| Cloud Run | `apexflow-api` | 2 CPU, 2 Gi, min 0 / max 1 instance, 80 concurrency |
| VPC Connector | `apexflow-vpc-connector` | `10.8.0.0/28`, `e2-micro`, 2-3 instances |
| Firewall Rule | `allow-vpc-connector-to-alloydb` | TCP 5432 from `10.8.0.0/28` |
| Secret | `apexflow-db-password` | DB password, accessed by `apexflow-api@` and `cloudbuild-ci@` |
| Service Account | `apexflow-api@` | Cloud Run runtime, Vertex AI + secret access |
| Service Account | `cloudbuild-ci@` | CI/CD, build + deploy + secret access |
| Service Account | `vm-scheduler@` | Nightly VM + Cloud Run stop |
| Cloud Scheduler | `vm-auto-stop` | `0 23 * * *` Asia/Kolkata, stops GCE VM |
| Cloud Scheduler | `cloudrun-auto-stop` | `0 23 * * *` Asia/Kolkata, sets Cloud Run ingress to internal-only |
| Cloud Build Connection | `apexflow-github` | GitHub OAuth, linked to repo |
| Cloud Build Trigger | `apexflow-ci` | Tag `^v.*$`, substitution: `_ALLOYDB_HOST` |
| Firebase Hosting | `apexflow-console` | Site in `apexflow-ai`, serves `frontend/dist`, rewrites `/api/**` to Cloud Run |
| Firebase Auth | Identity Platform | Google sign-in provider, authorized domains: localhost + `*.web.app` |
| APIs Enabled | 10 APIs | compute, run, vpcaccess, artifactregistry, secretmanager, cloudbuild, cloudscheduler, firebase, identitytoolkit, iap |
