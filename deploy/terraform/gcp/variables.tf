variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "domain_name" {
  description = "Public DNS name for the load balancer"
  type        = string
}

variable "db_password" {
  description = "Cloud SQL password for user `ec`"
  type        = string
  sensitive   = true
}

variable "db_tier" {
  description = "Cloud SQL machine type"
  type        = string
  default     = "db-custom-2-7680"  # 2 vCPU / 7.5 GB
}

variable "db_ha" {
  description = "Enable Regional HA (recommended for prod)"
  type        = bool
  default     = false
}

variable "backend_image_tag" {
  description = "Backend image tag in Artifact Registry"
  type        = string
  default     = "latest"
}

variable "frontend_image_tag" {
  description = "Frontend image tag in Artifact Registry"
  type        = string
  default     = "latest"
}

variable "backend_min_instances" {
  description = "Cloud Run backend min instances (>=1 to avoid cold starts)"
  type        = number
  default     = 2
}

variable "backend_max_instances" {
  description = "Cloud Run backend max instances"
  type        = number
  default     = 10
}

variable "backend_cpu" {
  description = "Backend CPU per Cloud Run instance"
  type        = string
  default     = "1"
}

variable "backend_memory" {
  description = "Backend memory per Cloud Run instance"
  type        = string
  default     = "1Gi"
}

variable "app_secret_key" {
  description = "FastAPI SECRET_KEY (64+ random bytes)"
  type        = string
  sensitive   = true
}

variable "app_encryption_key" {
  description = "Application encryption key"
  type        = string
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Anthropic API key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  sensitive   = true
  default     = ""
}
