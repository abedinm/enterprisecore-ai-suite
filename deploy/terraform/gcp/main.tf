# EnterpriseCore AI Suite — GCP deployment (Cloud Run + Cloud SQL + GCS).
#
# Spins up:
#   - Artifact Registry repo for backend + frontend images
#   - Cloud SQL (Postgres 16)
#   - Memorystore Redis
#   - Cloud Storage bucket for uploads (CMEK-encrypted)
#   - Cloud Run services for backend + frontend
#   - HTTPS Load Balancer with Google-managed TLS cert
#   - Secret Manager for application secrets
#
# Variables you must set:
#   - project_id
#   - region
#   - domain_name
#   - db_password

terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.36"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  name = "enterprisecore"
}

# ---------------------------------------------------------------------------
# Enable APIs
# ---------------------------------------------------------------------------
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "redis.googleapis.com",
    "compute.googleapis.com",
    "servicenetworking.googleapis.com",
    "cloudkms.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# ---------------------------------------------------------------------------
# KMS for CMEK
# ---------------------------------------------------------------------------
resource "google_kms_key_ring" "this" {
  name     = "${local.name}-kr"
  location = var.region
  depends_on = [google_project_service.apis]
}

resource "google_kms_crypto_key" "data" {
  name            = "${local.name}-data"
  key_ring        = google_kms_key_ring.this.id
  rotation_period = "7776000s"  # 90 days
}

# ---------------------------------------------------------------------------
# Artifact Registry
# ---------------------------------------------------------------------------
resource "google_artifact_registry_repository" "this" {
  location      = var.region
  repository_id = "${local.name}-images"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

# ---------------------------------------------------------------------------
# Private VPC for Cloud SQL + Redis
# ---------------------------------------------------------------------------
resource "google_compute_network" "this" {
  name                    = "${local.name}-net"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.apis]
}

resource "google_compute_subnetwork" "this" {
  name          = "${local.name}-subnet"
  ip_cidr_range = "10.20.0.0/20"
  region        = var.region
  network       = google_compute_network.this.id
  private_ip_google_access = true
}

resource "google_compute_global_address" "private_ip" {
  name          = "${local.name}-private-ip"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.this.id
}

resource "google_service_networking_connection" "this" {
  network                 = google_compute_network.this.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip.name]
}

# ---------------------------------------------------------------------------
# Cloud SQL (Postgres)
# ---------------------------------------------------------------------------
resource "google_sql_database_instance" "this" {
  name             = "${local.name}-db"
  database_version = "POSTGRES_16"
  region           = var.region
  deletion_protection = true

  settings {
    tier              = var.db_tier
    availability_type = var.db_ha ? "REGIONAL" : "ZONAL"
    disk_size         = 50
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      backup_retention_settings {
        retained_backups = 14
      }
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.this.id
    }
  }

  depends_on = [google_service_networking_connection.this]
}

resource "google_sql_database" "this" {
  name     = "enterprisecore"
  instance = google_sql_database_instance.this.name
}

resource "google_sql_user" "this" {
  name     = "ec"
  instance = google_sql_database_instance.this.name
  password = var.db_password
}

# ---------------------------------------------------------------------------
# Memorystore Redis
# ---------------------------------------------------------------------------
resource "google_redis_instance" "this" {
  name           = "${local.name}-redis"
  tier           = "BASIC"
  memory_size_gb = 1
  region         = var.region

  authorized_network = google_compute_network.this.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  redis_version      = "REDIS_7_0"

  depends_on = [google_service_networking_connection.this]
}

# ---------------------------------------------------------------------------
# GCS uploads bucket
# ---------------------------------------------------------------------------
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "google_storage_bucket" "uploads" {
  name          = "${local.name}-uploads-${random_id.bucket_suffix.hex}"
  location      = var.region
  storage_class = "STANDARD"
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  encryption {
    default_kms_key_name = google_kms_crypto_key.data.id
  }

  lifecycle_rule {
    condition { age = 365 }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  depends_on = [google_kms_crypto_key_iam_member.gcs]
}

# Storage service agent must be able to use the KMS key
data "google_storage_project_service_account" "this" {}

resource "google_kms_crypto_key_iam_member" "gcs" {
  crypto_key_id = google_kms_crypto_key.data.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${data.google_storage_project_service_account.this.email_address}"
}

# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------
resource "google_secret_manager_secret" "secret_key" {
  secret_id = "${local.name}-secret-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "secret_key" {
  secret      = google_secret_manager_secret.secret_key.id
  secret_data = var.app_secret_key
}

resource "google_secret_manager_secret" "encryption_key" {
  secret_id = "${local.name}-encryption-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "encryption_key" {
  secret      = google_secret_manager_secret.encryption_key.id
  secret_data = var.app_encryption_key
}

resource "google_secret_manager_secret" "db_password" {
  secret_id = "${local.name}-db-password"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password
}

resource "google_secret_manager_secret" "anthropic_key" {
  count     = var.anthropic_api_key == "" ? 0 : 1
  secret_id = "${local.name}-anthropic-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "anthropic_key" {
  count       = var.anthropic_api_key == "" ? 0 : 1
  secret      = google_secret_manager_secret.anthropic_key[0].id
  secret_data = var.anthropic_api_key
}

# ---------------------------------------------------------------------------
# Service account for Cloud Run
# ---------------------------------------------------------------------------
resource "google_service_account" "run" {
  account_id   = "${local.name}-run"
  display_name = "EnterpriseCore Cloud Run runtime"
}

resource "google_project_iam_member" "run_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.run.email}"
}

resource "google_project_iam_member" "run_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.run.email}"
}

resource "google_storage_bucket_iam_member" "run_uploads" {
  bucket = google_storage_bucket.uploads.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.run.email}"
}

# ---------------------------------------------------------------------------
# Serverless VPC connector (Cloud Run -> private services)
# ---------------------------------------------------------------------------
resource "google_vpc_access_connector" "this" {
  name          = "${local.name}-conn"
  region        = var.region
  network       = google_compute_network.this.name
  ip_cidr_range = "10.21.0.0/28"
  min_instances = 2
  max_instances = 3
}

# ---------------------------------------------------------------------------
# Cloud Run — backend
# ---------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "backend" {
  name     = "${local.name}-backend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.run.email

    scaling {
      min_instance_count = var.backend_min_instances
      max_instance_count = var.backend_max_instances
    }

    vpc_access {
      connector = google_vpc_access_connector.this.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.this.repository_id}/backend:${var.backend_image_tag}"

      ports {
        container_port = 8765
      }

      resources {
        limits = {
          cpu    = var.backend_cpu
          memory = var.backend_memory
        }
        cpu_idle = true
      }

      env {
        name  = "APP_ENV"
        value = "production"
      }
      env {
        name  = "DB_BACKEND"
        value = "postgres"
      }
      env {
        name  = "LOG_FORMAT"
        value = "json"
      }
      env {
        name  = "CORS_ORIGINS"
        value = "https://${var.domain_name}"
      }
      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.uploads.name
      }
      env {
        name  = "POSTGRES_DSN"
        value = "postgresql+psycopg2://ec:$(DB_PASSWORD)@${google_sql_database_instance.this.private_ip_address}:5432/enterprisecore"
      }
      env {
        name  = "REDIS_URL"
        value = "redis://${google_redis_instance.this.host}:${google_redis_instance.this.port}/0"
      }
      env {
        name = "SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secret_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "ENCRYPTION_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.encryption_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get {
          path = "/api/health"
        }
        initial_delay_seconds = 10
        period_seconds        = 5
        failure_threshold     = 24
      }
      liveness_probe {
        http_get {
          path = "/api/health"
        }
        period_seconds = 30
      }
    }
  }

  depends_on = [google_project_iam_member.run_secret_accessor]
}

# ---------------------------------------------------------------------------
# Cloud Run — frontend
# ---------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "frontend" {
  name     = "${local.name}-frontend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    scaling {
      min_instance_count = 1
      max_instance_count = 5
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.this.repository_id}/frontend:${var.frontend_image_tag}"
      ports {
        container_port = 80
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "256Mi"
        }
        cpu_idle = true
      }
    }
  }
}

# ---------------------------------------------------------------------------
# HTTPS Load Balancer
# ---------------------------------------------------------------------------
resource "google_compute_region_network_endpoint_group" "backend" {
  name                  = "${local.name}-backend-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.backend.name
  }
}

resource "google_compute_region_network_endpoint_group" "frontend" {
  name                  = "${local.name}-frontend-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.frontend.name
  }
}

resource "google_compute_backend_service" "backend" {
  name                  = "${local.name}-backend-bes"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  backend {
    group = google_compute_region_network_endpoint_group.backend.id
  }
  log_config {
    enable = true
  }
}

resource "google_compute_backend_service" "frontend" {
  name                  = "${local.name}-frontend-bes"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  backend {
    group = google_compute_region_network_endpoint_group.frontend.id
  }
  log_config {
    enable = true
  }
}

resource "google_compute_url_map" "this" {
  name            = "${local.name}-urlmap"
  default_service = google_compute_backend_service.frontend.id

  host_rule {
    hosts        = [var.domain_name]
    path_matcher = "main"
  }

  path_matcher {
    name            = "main"
    default_service = google_compute_backend_service.frontend.id

    path_rule {
      paths   = ["/api/*", "/site/*", "/widget.js", "/metrics"]
      service = google_compute_backend_service.backend.id
    }
  }
}

resource "google_compute_managed_ssl_certificate" "this" {
  name = "${local.name}-cert"
  managed {
    domains = [var.domain_name]
  }
}

resource "google_compute_target_https_proxy" "this" {
  name             = "${local.name}-https-proxy"
  url_map          = google_compute_url_map.this.id
  ssl_certificates = [google_compute_managed_ssl_certificate.this.id]
}

resource "google_compute_global_address" "lb" {
  name = "${local.name}-lb-ip"
}

resource "google_compute_global_forwarding_rule" "this" {
  name                  = "${local.name}-https"
  target                = google_compute_target_https_proxy.this.id
  port_range            = "443"
  ip_address            = google_compute_global_address.lb.address
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

# HTTP -> HTTPS redirect
resource "google_compute_url_map" "redirect" {
  name = "${local.name}-redirect"
  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

resource "google_compute_target_http_proxy" "redirect" {
  name    = "${local.name}-http-proxy"
  url_map = google_compute_url_map.redirect.id
}

resource "google_compute_global_forwarding_rule" "redirect" {
  name                  = "${local.name}-http"
  target                = google_compute_target_http_proxy.redirect.id
  port_range            = "80"
  ip_address            = google_compute_global_address.lb.address
  load_balancing_scheme = "EXTERNAL_MANAGED"
}
