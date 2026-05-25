output "backend_fqdn" {
  description = "Container App backend FQDN (proxy your custom domain here)"
  value       = azurerm_container_app.backend.latest_revision_fqdn
}

output "frontend_fqdn" {
  description = "Container App frontend FQDN"
  value       = azurerm_container_app.frontend.latest_revision_fqdn
}

output "container_registry_url" {
  description = "ACR login server"
  value       = azurerm_container_registry.this.login_server
}

output "postgres_fqdn" {
  description = "Postgres flexible server FQDN"
  value       = azurerm_postgresql_flexible_server.this.fqdn
}

output "redis_hostname" {
  description = "Redis hostname"
  value       = azurerm_redis_cache.this.hostname
}

output "key_vault_uri" {
  description = "Key Vault URI"
  value       = azurerm_key_vault.this.vault_uri
}

output "storage_account_name" {
  description = "Storage account holding the uploads container"
  value       = azurerm_storage_account.uploads.name
}
