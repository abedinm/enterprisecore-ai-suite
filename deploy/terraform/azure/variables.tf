variable "location" {
  description = "Azure region"
  type        = string
  default     = "eastus"
}

variable "domain_name" {
  description = "Public DNS name (configured via Azure Front Door or your own CNAME to the Container App FQDN)"
  type        = string
}

variable "db_password" {
  description = "Postgres admin password"
  type        = string
  sensitive   = true
}

variable "db_sku" {
  description = "Postgres Flexible Server SKU"
  type        = string
  default     = "GP_Standard_D2s_v3"
}

variable "db_ha" {
  description = "Enable Zone-Redundant HA"
  type        = bool
  default     = false
}

variable "backend_image_tag" {
  description = "Backend image tag in ACR"
  type        = string
  default     = "latest"
}

variable "frontend_image_tag" {
  description = "Frontend image tag in ACR"
  type        = string
  default     = "latest"
}

variable "backend_min_replicas" {
  description = "Container App backend min replicas"
  type        = number
  default     = 2
}

variable "backend_max_replicas" {
  description = "Container App backend max replicas"
  type        = number
  default     = 10
}

variable "backend_cpu" {
  description = "Backend vCPU"
  type        = number
  default     = 0.5
}

variable "backend_memory" {
  description = "Backend memory"
  type        = string
  default     = "1Gi"
}

variable "app_secret_key" {
  description = "FastAPI SECRET_KEY (64+ bytes of randomness)"
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
