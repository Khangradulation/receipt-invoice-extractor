locals {
  labels = {
    app = "receipt-extractor"
    env = var.environment
  }
  documents_bucket = "${var.project_id}-documents"
  dataset_id       = "receipt_analytics"
  sa               = module.service_accounts.members
  sa_email         = module.service_accounts.emails
  gcs_agent        = "serviceAccount:service-${var.project_number}@gs-project-accounts.iam.gserviceaccount.com"
  pubsub_agent     = "serviceAccount:service-${var.project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"
  # Cloud Run's deterministic URLs (https://SERVICE-PROJECT_NUMBER.REGION.run.app), known before
  # the services exist, so CORS and sign-in can allow the web app on the first apply.
  frontend_host = "receipt-frontend-${var.project_number}.${var.region}.run.app"
  api_url       = "https://receipt-api-${var.project_number}.${var.region}.run.app"
  web_origins   = distinct(concat(var.web_origins, ["https://${local.frontend_host}"]))
  app_env = {
    ENVIRONMENT          = var.environment
    LOG_LEVEL            = "INFO"
    GCP_PROJECT_ID       = var.project_id
    GCS_UPLOAD_BUCKET    = local.documents_bucket
    GEMINI_MODEL         = var.gemini_model
    GEMINI_LOCATION      = var.gemini_location
    SUPPORTED_CURRENCIES = join(",", var.supported_currencies)
  }
}

module "services" {
  source     = "../project_services"
  project_id = var.project_id
  services = [
    "aiplatform.googleapis.com", "artifactregistry.googleapis.com", "bigquery.googleapis.com",
    "billingbudgets.googleapis.com", "cloudbilling.googleapis.com", "cloudbuild.googleapis.com",
    "cloudfunctions.googleapis.com", "cloudresourcemanager.googleapis.com",
    "eventarc.googleapis.com", "firebase.googleapis.com", "firestore.googleapis.com",
    "iam.googleapis.com", "iamcredentials.googleapis.com", "identitytoolkit.googleapis.com",
    "logging.googleapis.com", "monitoring.googleapis.com", "pubsub.googleapis.com",
    "run.googleapis.com", "secretmanager.googleapis.com", "storage.googleapis.com",
    "sts.googleapis.com",
  ]
}

module "service_accounts" {
  source     = "../service_accounts"
  project_id = var.project_id
  accounts = {
    "receipt-api"      = "Receipt extractor API (Cloud Run)"
    "receipt-worker"   = "Receipt extractor worker (Cloud Run)"
    "receipt-eventarc" = "Receipt extractor Eventarc trigger (invokes the worker)"
    "receipt-build"    = "Receipt extractor image builds (Cloud Build)"
    "receipt-frontend" = "Receipt extractor web app (Cloud Run)"
  }
}

# --- Storage ---------------------------------------------------------------------------------
module "documents" {
  source       = "../storage"
  project_id   = var.project_id
  name         = local.documents_bucket
  location     = var.region
  cors_origins = local.web_origins
  labels       = merge(local.labels, { component = "documents" })
  iam_members = [
    # Create (uploads), read (previews) and delete (user deletion, every version) on this bucket.
    { role = "roles/storage.objectUser", member = local.sa["receipt-api"] },
    { role = "roles/storage.objectViewer", member = local.sa["receipt-worker"] },
  ]
}

resource "google_storage_bucket" "cloudbuild" {
  project                     = var.project_id
  name                        = "${var.project_id}_cloudbuild"
  location                    = upper(var.region)
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = merge(local.labels, { component = "build-staging" })
  lifecycle_rule {
    action { type = "Delete" }
    condition { age = 30 }
  }
}

resource "google_storage_bucket_iam_member" "cloudbuild_reader" {
  bucket = google_storage_bucket.cloudbuild.name
  role   = "roles/storage.objectViewer"
  member = local.sa["receipt-build"]
}

# --- Data ------------------------------------------------------------------------------------
module "firestore" {
  source     = "../firestore"
  project_id = var.project_id
  location   = var.region
}

module "bigquery" {
  source     = "../bigquery"
  project_id = var.project_id
  dataset_id = local.dataset_id
  location   = "US"
  labels     = local.labels
  iam_members = [
    { role = "roles/bigquery.dataEditor", member = local.sa["receipt-worker"] },
    { role = "roles/bigquery.dataEditor", member = local.sa["receipt-api"] },
  ]
}

# --- Images ----------------------------------------------------------------------------------
module "registry" {
  source         = "../artifact_registry"
  project_id     = var.project_id
  location       = var.region
  repository_id  = "receipt-extractor"
  labels         = local.labels
  writer_members = [local.sa["receipt-build"], "serviceAccount:${module.github_wif.deployer_email}"]
}

# --- Services --------------------------------------------------------------------------------
module "worker" {
  source          = "../cloud_run_service"
  project_id      = var.project_id
  location        = var.region
  name            = "receipt-worker"
  image           = var.initial_image
  service_account = local.sa_email["receipt-worker"]
  ingress         = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  invoker_members = [local.sa["receipt-eventarc"]]
  memory          = "1Gi"
  concurrency     = 4
  timeout_seconds = 300
  max_instances   = 3
  env             = local.app_env
  labels          = { app = "receipt-extractor", component = "worker" }
}

module "upload_trigger" {
  source          = "../eventarc_gcs_trigger"
  project_id      = var.project_id
  location        = var.region
  name            = "receipt-upload-finalized"
  bucket          = module.documents.name
  service         = module.worker.name
  path            = "/events/storage"
  service_account = local.sa_email["receipt-eventarc"]
}

module "api" {
  source          = "../cloud_run_service"
  project_id      = var.project_id
  location        = var.region
  name            = "receipt-api"
  image           = var.initial_image
  service_account = local.sa_email["receipt-api"]
  ingress         = "INGRESS_TRAFFIC_ALL"
  invoker_members = ["allUsers"] # public; every endpoint except /health requires a Firebase token
  memory          = "512Mi"
  concurrency     = 40
  timeout_seconds = 60
  max_instances   = 3
  env = merge(local.app_env, {
    SIGNING_SERVICE_ACCOUNT = local.sa_email["receipt-api"]
    FIREBASE_PROJECT_ID     = var.project_id
    CORS_ALLOWED_ORIGINS    = join(",", local.web_origins)
  })
  labels = { app = "receipt-extractor", component = "api" }
}

module "frontend" {
  source          = "../cloud_run_service"
  project_id      = var.project_id
  location        = var.region
  name            = "receipt-frontend"
  image           = var.initial_image
  service_account = local.sa_email["receipt-frontend"]
  ingress         = "INGRESS_TRAFFIC_ALL"
  invoker_members = ["allUsers"]
  memory          = "256Mi"
  max_instances   = 2
  labels          = { app = "receipt-extractor", component = "frontend" }
}

# --- IAM -------------------------------------------------------------------------------------
module "project_iam" {
  source     = "../project_iam"
  project_id = var.project_id
  bindings = [
    { role = "roles/datastore.user", member = local.sa["receipt-api"] },
    { role = "roles/bigquery.jobUser", member = local.sa["receipt-api"] },
    { role = "roles/datastore.user", member = local.sa["receipt-worker"] },
    { role = "roles/aiplatform.user", member = local.sa["receipt-worker"] },
    { role = "roles/bigquery.jobUser", member = local.sa["receipt-worker"] },
    { role = "roles/eventarc.eventReceiver", member = local.sa["receipt-eventarc"] },
    { role = "roles/logging.logWriter", member = local.sa["receipt-build"] },
    # Direct Cloud Storage events are published by the Cloud Storage service agent.
    { role = "roles/pubsub.publisher", member = local.gcs_agent },
    # The Pub/Sub service agent mints the OIDC tokens Eventarc uses to call Cloud Run.
    { role = "roles/iam.serviceAccountTokenCreator", member = local.pubsub_agent },
  ]
}

# The API signs upload/download URLs as itself through IAM signBlob (no keys). Developers may do
# the same when running the API locally.
resource "google_service_account_iam_member" "api_signers" {
  for_each           = toset(concat([local.sa["receipt-api"]], var.developer_members))
  service_account_id = module.service_accounts.names["receipt-api"]
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = each.value
}

# --- CI/CD (GitHub Actions via Workload Identity Federation) ----------------------------------
module "github_wif" {
  source             = "../github_wif"
  project_id         = var.project_id
  github_repository  = var.github_repository
  github_owner_id    = var.github_owner_id
  github_environment = var.github_environment
  deployer_roles     = ["roles/run.developer"]
  act_as_service_accounts = [
    local.sa_email["receipt-api"], local.sa_email["receipt-worker"], local.sa_email["receipt-frontend"],
  ]
  terraform_runner_roles = var.terraform_runner_roles
}

# --- Cost guard, auth, monitoring -------------------------------------------------------------
module "budget_guard" {
  source          = "../budget_guard"
  project_id      = var.project_id
  project_number  = var.project_number
  billing_account = var.billing_account
  amount          = var.budget_amount
  display_name    = format("Receipt Extractor $%d cap (auto-stop)", var.budget_amount)
}

module "identity" {
  source             = "../identity"
  project_id         = var.project_id
  authorized_domains = distinct(concat(var.auth_domains, [local.frontend_host, "${var.project_id}.firebaseapp.com", "${var.project_id}.web.app"]))
}

module "monitoring" {
  source                = "../monitoring"
  project_id            = var.project_id
  notification_channels = var.notification_channels
}
