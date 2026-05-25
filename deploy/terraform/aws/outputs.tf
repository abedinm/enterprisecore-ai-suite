output "alb_dns_name" {
  description = "ALB DNS — create an A/ALIAS record pointing var.domain_name here"
  value       = aws_lb.this.dns_name
}

output "alb_zone_id" {
  description = "ALB hosted zone ID (for Route 53 ALIAS records)"
  value       = aws_lb.this.zone_id
}

output "rds_endpoint" {
  description = "RDS endpoint"
  value       = aws_db_instance.this.endpoint
}

output "redis_endpoint" {
  description = "Redis primary endpoint"
  value       = aws_elasticache_cluster.this.cache_nodes[0].address
}

output "ecr_backend_url" {
  description = "ECR repository for the backend container"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend_url" {
  description = "ECR repository for the frontend container"
  value       = aws_ecr_repository.frontend.repository_url
}

output "s3_uploads_bucket" {
  description = "S3 bucket for user uploads"
  value       = aws_s3_bucket.uploads.bucket
}

output "kms_key_arn" {
  description = "KMS key used for all encrypted resources"
  value       = aws_kms_key.data.arn
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.this.name
}
