terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------

variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "us-central1"
}
variable "image_uri" {
  type        = string
  description = "Full Artifact Registry image URI, e.g. us-central1-docker.pkg.dev/PROJECT/REPO/product-intel-agent:latest"
}
variable "serper_api_key" {
  type      = string
  sensitive = true
}

# ---------------------------------------------------------------------------
# Enable required APIs
# ---------------------------------------------------------------------------

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "aiplatform.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# ---------------------------------------------------------------------------
# Secret Manager — Serper API Key
# ---------------------------------------------------------------------------

resource "google_secret_manager_secret" "serper_key" {
  secret_id = "serper-api-key"
  replication { auto {} }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "serper_key_v1" {
  secret      = google_secret_manager_secret.serper_key.id
  secret_data = var.serper_api_key
}

# ---------------------------------------------------------------------------
# GCS Bucket — AI Assets
# ---------------------------------------------------------------------------

resource "google_storage_bucket" "ai_assets" {
  name          = "${var.project_id}-intel-assets"
  location      = var.region
  force_destroy = false
}

# ---------------------------------------------------------------------------
# Cloud Run — Agent Service
# ---------------------------------------------------------------------------

resource "google_service_account" "agent_sa" {
  account_id   = "product-intel-agent-sa"
  display_name = "Product Intel Agent Runtime SA"
}

resource "google_project_iam_member" "agent_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "agent_secret_accessor" {
  secret_id = google_secret_manager_secret.serper_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_sa.email}"
}

resource "google_storage_bucket_iam_member" "agent_bucket_admin" {
  bucket = google_storage_bucket.ai_assets.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.agent_sa.email}"
}

resource "google_cloud_run_v2_service" "agent" {
  name     = "product-intel-agent"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.agent_sa.email
    containers {
      image = var.image_uri

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name  = "AI_ASSETS_BUCKET"
        value = google_storage_bucket.ai_assets.name
      }
      env {
        name = "SERPER_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.serper_key.secret_id
            version = "latest"
          }
        }
      }
    }
  }
  depends_on = [google_project_service.apis]
}

# ---------------------------------------------------------------------------
# Cloud Scheduler — Daily trigger at 08:30 Asia/Taipei
# ---------------------------------------------------------------------------

resource "google_cloud_scheduler_job" "daily_intel" {
  name      = "product-intel-daily"
  schedule  = "30 8 * * *"
  time_zone = "Asia/Taipei"
  region    = var.region

  http_target {
    uri         = "${google_cloud_run_v2_service.agent.uri}/analyze"
    http_method = "POST"
    body        = base64encode(jsonencode({ competitor = "your-main-competitor", session_id = "scheduled" }))
    headers     = { "Content-Type" = "application/json" }

    oidc_token {
      service_account_email = google_service_account.scheduler_sa.email
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_service_account" "scheduler_sa" {
  account_id   = "intel-scheduler-sa"
  display_name = "Product Intel Scheduler SA"
}

resource "google_cloud_run_v2_service_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.agent.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler_sa.email}"
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "cloud_run_url" {
  value = google_cloud_run_v2_service.agent.uri
}

output "ai_assets_bucket" {
  value = google_storage_bucket.ai_assets.name
}
