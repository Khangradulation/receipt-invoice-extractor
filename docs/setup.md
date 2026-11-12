# Setup

Part A runs everything locally with no cloud project. Part B creates a Google Cloud environment and
connects local development and CI to it.

## Prerequisites

| Tool | Version | Needed for |
| --- | --- | --- |
| [uv](https://docs.astral.sh/uv/) | 0.13+ | Backend (installs Python 3.12 from `backend/.python-version`) |
| Node.js | 24 LTS+ (npm 10+) | Frontend |
| Google Cloud SDK | recent | Anything that touches GCP |
| Terraform | 1.9+ (CI uses 1.17.1) | Infrastructure |
| GitHub CLI (`gh`) | recent | Configuring CI environments |
| Docker with buildx | 24+ | Optional: `docker compose`, `make docker-build` |

## Part A — local development

### 1. Install and configure

```bash
git clone https://github.com/OWNER/receipt-invoice-extractor.git && cd receipt-invoice-extractor
cp .env.example .env
make install            # cd backend && uv sync; cd frontend && npm ci
```

There's one `.env` file at the repository root. The backend reads it through
`receipt_shared.config.Settings`; Vite only exposes `VITE_*` values to the browser. Every variable is
documented in `.env.example`.

### 2. Run the services

```bash
make api      # http://localhost:8080/api/v1/health   docs: http://localhost:8080/api/v1/docs
make worker   # http://localhost:8081/health
make web      # http://localhost:5173  (proxies /api to VITE_API_PROXY_TARGET, default :8080)
```

Without a cloud project, the API's health check and docs work, and the web app shows its sign-in
screen. Signing in, uploading and processing need Part B.

### 3. Run the checks

```bash
make check     # ruff, mypy, pytest (+ coverage ≥ 90%), eslint, prettier, tsc, vitest, build, terraform
make audit     # pip-audit + npm audit
```

### 4. Try extraction without the cloud

```bash
make samples                                                    # synthetic PDFs/PNGs + ground truth
cd backend && uv run receipt-extract --inspect-only ../evaluation/samples/out/*.pdf
```

`--inspect-only` runs the file checks without calling Gemini.

## Part B — a Google Cloud environment

> The original dev project was built step by step across the phases: scripts first, adopted by
> Terraform in Phase 11. The sequence below is the consolidated path for a **new** project. Each
> command is the one used in this repository, but the sequence as a whole has not been re-run
> from scratch.

Set these once per shell:

```bash
export PROJECT_ID=my-receipts-dev
export REGION=us-central1
export BILLING_ACCOUNT=XXXXXX-XXXXXX-XXXXXX      # gcloud billing accounts list
```

### 1. Project and billing

```bash
gcloud projects create "$PROJECT_ID"
gcloud billing projects link "$PROJECT_ID" --billing-account "$BILLING_ACCOUNT"
gcloud config set project "$PROJECT_ID"
gcloud auth application-default login
gcloud auth application-default set-quota-project "$PROJECT_ID"
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
```

### 2. Terraform state bucket

```bash
PROJECT_ID="$PROJECT_ID" ./ops/gcp/bootstrap-tfstate.sh        # versioned, private: $PROJECT_ID-tfstate
```

### 3. Enable the Firebase APIs

Terraform enables everything else. These two must be on before Firebase is added:

```bash
gcloud services enable firebase.googleapis.com identitytoolkit.googleapis.com
```

### 4. Firebase Authentication

```bash
TOKEN=$(gcloud auth print-access-token)
H=(-H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT_ID" -H "Content-Type: application/json")

# Add Firebase to the project and initialise Authentication (Identity Platform)
curl -s -X POST "${H[@]}" "https://firebase.googleapis.com/v1beta1/projects/$PROJECT_ID:addFirebase" -d '{}'
curl -s -X POST "${H[@]}" "https://identitytoolkit.googleapis.com/v2/projects/$PROJECT_ID/identityPlatform:initializeAuth" -d '{}'

# Create the web app, then print its config (apiKey, authDomain, appId)
curl -s -X POST "${H[@]}" "https://firebase.googleapis.com/v1beta1/projects/$PROJECT_ID/webApps" \
  -d '{"displayName": "Receipt Extractor"}'
APP_ID=$(curl -s "${H[@]}" "https://firebase.googleapis.com/v1beta1/projects/$PROJECT_ID/webApps" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["apps"][0]["appId"])')
curl -s "${H[@]}" "https://firebase.googleapis.com/v1beta1/projects/$PROJECT_ID/webApps/$APP_ID/config"
```

The Firebase console does the same thing (Add project → existing GCP project, Authentication → Get
started, Project settings → Add web app). Terraform then enables email/password sign-in and sets
the authorised domains (`terraform/modules/identity`).

### 5. Terraform

```bash
cd terraform/environments/dev
rm imports.tf          # it only adopts the original project's script-built resources
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`. It's git-ignored, so it never reaches the repository.

```hcl
project_id        = "my-receipts-dev"
project_number    = "123456789012"            # echo $PROJECT_NUMBER
billing_account   = "XXXXXX-XXXXXX-XXXXXX"
github_repository = "OWNER/receipt-invoice-extractor"
github_owner_id   = "12345678"                # gh api users/OWNER -q .id
developer_members = ["user:you@example.com"]  # may sign upload URLs when running the API locally
alert_emails      = ["you@example.com"]       # monitoring alerts
```

```bash
terraform init -backend-config="bucket=$PROJECT_ID-tfstate"
terraform plan         # review it
terraform apply
terraform output       # WIF provider, CI deployer, frontend/API URLs, dashboard
cd ../../..
```

The three Cloud Run services start with Google's placeholder image. The first CI deploy replaces
them (step 8).

### 6. Budget kill switch

Terraform creates the budget, the Pub/Sub topic and the function's account and permissions. Deploy
the function's code with the command in
[ops/budget-kill-switch/README.md](../ops/budget-kill-switch/README.md#deploy--update), then send it the
below-budget test message described there.

### 7. Local `.env` against the project

```bash
GCP_PROJECT_ID=my-receipts-dev
GCP_REGION=us-central1
GCS_UPLOAD_BUCKET=my-receipts-dev-documents
SIGNING_SERVICE_ACCOUNT=receipt-api@my-receipts-dev.iam.gserviceaccount.com
FIREBASE_PROJECT_ID=my-receipts-dev
VITE_FIREBASE_API_KEY=...            # from step 4
VITE_FIREBASE_AUTH_DOMAIN=my-receipts-dev.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=my-receipts-dev
VITE_FIREBASE_APP_ID=...
```

Restart `make api` and `make web`, open <http://localhost:5173> and choose **Create account**.
Locally the API runs as you (ADC); `developer_members` lets you sign upload URLs as the API's
service account. Uploads are processed by the deployed worker, after step 8.

### 8. GitHub Actions

```bash
REPO=OWNER/receipt-invoice-extractor
gh api -X PUT repos/$REPO/environments/dev \
  -F 'deployment_branch_policy[protected_branches]=false' \
  -F 'deployment_branch_policy[custom_branch_policies]=true'
gh api -X POST repos/$REPO/environments/dev/deployment-branch-policies -f name=main -f type=branch

for kv in \
  "GCP_PROJECT_ID=$PROJECT_ID" "GCP_PROJECT_NUMBER=$PROJECT_NUMBER" "GCP_REGION=$REGION" \
  "GCP_WIF_PROVIDER=$(terraform -chdir=terraform/environments/dev output -raw github_wif_provider)" \
  "GCP_DEPLOYER_SA=$(terraform -chdir=terraform/environments/dev output -raw ci_deployer_email)" \
  "VITE_FIREBASE_API_KEY=..." "VITE_FIREBASE_AUTH_DOMAIN=$PROJECT_ID.firebaseapp.com" "VITE_FIREBASE_APP_ID=..."; do
  gh variable set "${kv%%=*}" --env dev --repo $REPO --body "${kv#*=}"
done
```

Merge to `main`, or run **Deploy dev** from the Actions tab. When it's green, open
`https://receipt-frontend-$PROJECT_NUMBER.$REGION.run.app`.

### 9. Verify

```bash
make smoke-test PROJECT_ID=$PROJECT_ID PROJECT_NUMBER=$PROJECT_NUMBER   # read-only
make test-e2e                                                            # full flow, a few cents
```

## Optional: containers locally

```bash
docker compose up --build
```

Builds the production images: frontend on <http://localhost:5173> (nginx), API on :8080, worker on
:8081.

## Repository layout

See the [README](../README.md#repository-structure).
