output "lb_ip_address" {
  description = "Static global IP of the HTTPS load balancer. Point your A record here."
  value       = google_compute_global_address.lb.address
}

output "backend_url" {
  description = "Direct Cloud Run URL for the backend (mostly for debugging)"
  value       = google_cloud_run_v2_service.backend.uri
}

output "frontend_url" {
  description = "Direct Cloud Run URL for the frontend"
  value       = google_cloud_run_v2_service.frontend.uri
}

output "artifact_registry_repository" {
  description = "Artifact Registry repo for pushing images"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.this.repository_id}"
}

output "sql_instance_connection_name" {
  description = "Cloud SQL connection name (for Cloud SQL Proxy)"
  value       = google_sql_database_instance.this.connection_name
}

output "uploads_bucket" {
  description = "GCS uploads bucket"
  value       = google_storage_bucket.uploads.name
}

output "redis_host" {
  description = "Memorystore Redis host"
  value       = google_redis_instance.this.host
}
