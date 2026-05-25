variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "domain_name" {
  description = "Public DNS name for the ALB (e.g. enterprisecore.example.com)"
  type        = string
}

variable "acm_certificate_arn" {
  description = "ARN of an ACM cert in the same region covering domain_name"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.40.0.0/16"
}

variable "db_password" {
  description = "Postgres master password"
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.medium"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GB"
  type        = number
  default     = 50
}

variable "db_multi_az" {
  description = "Whether to enable Multi-AZ on RDS (recommended for prod)"
  type        = bool
  default     = false
}

variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t4g.micro"
}

variable "backend_image_tag" {
  description = "Backend container tag in ECR"
  type        = string
  default     = "latest"
}

variable "frontend_image_tag" {
  description = "Frontend container tag in ECR"
  type        = string
  default     = "latest"
}

variable "backend_cpu" {
  description = "Backend task CPU (Fargate units; 1024 = 1 vCPU)"
  type        = number
  default     = 512
}

variable "backend_memory" {
  description = "Backend task memory in MB"
  type        = number
  default     = 1024
}

variable "backend_desired_count" {
  description = "Backend service desired task count"
  type        = number
  default     = 2
}

variable "backend_max_capacity" {
  description = "Max backend tasks under autoscaling"
  type        = number
  default     = 10
}

variable "frontend_desired_count" {
  description = "Frontend service desired task count"
  type        = number
  default     = 2
}

variable "app_secret_key" {
  description = "FastAPI SECRET_KEY (sign cookies + JWTs). Generate 64+ random bytes."
  type        = string
  sensitive   = true
}

variable "app_encryption_key" {
  description = "Application column-level encryption key. Generate 32+ random bytes."
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

variable "tags" {
  description = "Extra tags applied to all resources"
  type        = map(string)
  default     = {}
}
