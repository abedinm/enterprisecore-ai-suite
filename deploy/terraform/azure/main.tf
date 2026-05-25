# EnterpriseCore AI Suite — Azure deployment (Container Apps + PostgreSQL Flexible).
#
# Spins up:
#   - Resource group
#   - Container Apps environment with managed VNet
#   - Container Apps for backend + frontend (autoscaling)
#   - Azure Database for PostgreSQL Flexible Server
#   - Azure Cache for Redis
#   - Storage account for uploads (blob, customer-managed key)
#   - Container Registry
#   - Key Vault for secrets

terraform {
  required_version = ">= 1.6"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
}

locals {
  name = "enterprisecore"
}

data "azurerm_client_config" "current" {}

resource "random_id" "suffix" {
  byte_length = 3
}

# ---------------------------------------------------------------------------
# Resource group + VNet
# ---------------------------------------------------------------------------
resource "azurerm_resource_group" "this" {
  name     = "${local.name}-rg"
  location = var.location
}

resource "azurerm_virtual_network" "this" {
  name                = "${local.name}-vnet"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "container_apps" {
  name                 = "container-apps"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.30.0.0/21"]

  delegation {
    name = "ca-delegation"
    service_delegation {
      name = "Microsoft.App/environments"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action"
      ]
    }
  }
}

resource "azurerm_subnet" "db" {
  name                 = "db"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.30.8.0/24"]
  service_endpoints    = ["Microsoft.Storage"]

  delegation {
    name = "db-delegation"
    service_delegation {
      name = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action"
      ]
    }
  }
}

resource "azurerm_private_dns_zone" "db" {
  name                = "${local.name}.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.this.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "db" {
  name                  = "${local.name}-db-dnslink"
  resource_group_name   = azurerm_resource_group.this.name
  private_dns_zone_name = azurerm_private_dns_zone.db.name
  virtual_network_id    = azurerm_virtual_network.this.id
}

# ---------------------------------------------------------------------------
# Container Registry
# ---------------------------------------------------------------------------
resource "azurerm_container_registry" "this" {
  name                = "${local.name}cr${random_id.suffix.hex}"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = "Standard"
  admin_enabled       = false
}

# ---------------------------------------------------------------------------
# Storage account (uploads)
# ---------------------------------------------------------------------------
resource "azurerm_storage_account" "uploads" {
  name                     = "${local.name}up${random_id.suffix.hex}"
  resource_group_name      = azurerm_resource_group.this.name
  location                 = azurerm_resource_group.this.location
  account_tier             = "Standard"
  account_replication_type = "ZRS"
  min_tls_version          = "TLS1_2"
  https_traffic_only_enabled  = true
  allow_nested_items_to_be_public = false

  blob_properties {
    versioning_enabled = true
    delete_retention_policy {
      days = 30
    }
  }
}

resource "azurerm_storage_container" "uploads" {
  name                  = "uploads"
  storage_account_id    = azurerm_storage_account.uploads.id
  container_access_type = "private"
}

# ---------------------------------------------------------------------------
# Key Vault for secrets
# ---------------------------------------------------------------------------
resource "azurerm_key_vault" "this" {
  name                = "${local.name}kv${random_id.suffix.hex}"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"
  enable_rbac_authorization = true
  purge_protection_enabled  = true
  soft_delete_retention_days = 30
}

# Give the deployer permission to write secrets
resource "azurerm_role_assignment" "kv_admin" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_key_vault_secret" "secret_key" {
  name         = "app-secret-key"
  value        = var.app_secret_key
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [azurerm_role_assignment.kv_admin]
}

resource "azurerm_key_vault_secret" "encryption_key" {
  name         = "app-encryption-key"
  value        = var.app_encryption_key
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [azurerm_role_assignment.kv_admin]
}

resource "azurerm_key_vault_secret" "db_password" {
  name         = "db-password"
  value        = var.db_password
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [azurerm_role_assignment.kv_admin]
}

resource "azurerm_key_vault_secret" "anthropic_key" {
  count        = var.anthropic_api_key == "" ? 0 : 1
  name         = "anthropic-key"
  value        = var.anthropic_api_key
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [azurerm_role_assignment.kv_admin]
}

# ---------------------------------------------------------------------------
# PostgreSQL Flexible Server
# ---------------------------------------------------------------------------
resource "azurerm_postgresql_flexible_server" "this" {
  name                          = "${local.name}-db-${random_id.suffix.hex}"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = azurerm_resource_group.this.location
  version                       = "16"
  delegated_subnet_id           = azurerm_subnet.db.id
  private_dns_zone_id           = azurerm_private_dns_zone.db.id
  administrator_login           = "ec"
  administrator_password        = var.db_password
  zone                          = "1"
  storage_mb                    = 65536
  storage_tier                  = "P10"
  sku_name                      = var.db_sku
  backup_retention_days         = 14
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = false

  high_availability {
    mode = var.db_ha ? "ZoneRedundant" : "Disabled"
  }

  depends_on = [azurerm_private_dns_zone_virtual_network_link.db]

  lifecycle {
    ignore_changes = [zone, high_availability[0].standby_availability_zone]
  }
}

resource "azurerm_postgresql_flexible_server_database" "this" {
  name      = "enterprisecore"
  server_id = azurerm_postgresql_flexible_server.this.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# ---------------------------------------------------------------------------
# Redis Cache
# ---------------------------------------------------------------------------
resource "azurerm_redis_cache" "this" {
  name                = "${local.name}-redis-${random_id.suffix.hex}"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  capacity            = 1
  family              = "C"
  sku_name            = "Basic"
  non_ssl_port_enabled = false
  minimum_tls_version = "1.2"
}

# ---------------------------------------------------------------------------
# Container Apps environment
# ---------------------------------------------------------------------------
resource "azurerm_log_analytics_workspace" "this" {
  name                = "${local.name}-logs"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_container_app_environment" "this" {
  name                       = "${local.name}-cae"
  resource_group_name        = azurerm_resource_group.this.name
  location                   = azurerm_resource_group.this.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
  infrastructure_subnet_id   = azurerm_subnet.container_apps.id
}

# ---------------------------------------------------------------------------
# Managed identity for Container Apps -> ACR + KV access
# ---------------------------------------------------------------------------
resource "azurerm_user_assigned_identity" "app" {
  name                = "${local.name}-app-mi"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.this.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_role_assignment" "kv_secrets" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_role_assignment" "blob_contributor" {
  scope                = azurerm_storage_account.uploads.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# ---------------------------------------------------------------------------
# Container App — backend
# ---------------------------------------------------------------------------
resource "azurerm_container_app" "backend" {
  name                         = "${local.name}-backend"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.this.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "secret-key"
    key_vault_secret_id = azurerm_key_vault_secret.secret_key.id
    identity            = azurerm_user_assigned_identity.app.id
  }
  secret {
    name                = "encryption-key"
    key_vault_secret_id = azurerm_key_vault_secret.encryption_key.id
    identity            = azurerm_user_assigned_identity.app.id
  }
  secret {
    name                = "db-password"
    key_vault_secret_id = azurerm_key_vault_secret.db_password.id
    identity            = azurerm_user_assigned_identity.app.id
  }

  ingress {
    external_enabled = true
    target_port      = 8765
    transport        = "http"
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.backend_min_replicas
    max_replicas = var.backend_max_replicas

    container {
      name   = "backend"
      image  = "${azurerm_container_registry.this.login_server}/enterprisecore-backend:${var.backend_image_tag}"
      cpu    = var.backend_cpu
      memory = var.backend_memory

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
        name  = "POSTGRES_DSN"
        value = "postgresql+psycopg2://ec@${azurerm_postgresql_flexible_server.this.name}:$(DB_PASSWORD)@${azurerm_postgresql_flexible_server.this.fqdn}:5432/enterprisecore?sslmode=require"
      }
      env {
        name  = "AZURE_STORAGE_ACCOUNT"
        value = azurerm_storage_account.uploads.name
      }
      env {
        name  = "AZURE_STORAGE_CONTAINER"
        value = azurerm_storage_container.uploads.name
      }
      env {
        name        = "SECRET_KEY"
        secret_name = "secret-key"
      }
      env {
        name        = "ENCRYPTION_KEY"
        secret_name = "encryption-key"
      }
      env {
        name        = "DB_PASSWORD"
        secret_name = "db-password"
      }

      readiness_probe {
        transport = "HTTP"
        path      = "/api/health"
        port      = 8765
      }
      liveness_probe {
        transport = "HTTP"
        path      = "/api/health"
        port      = 8765
      }
    }

    http_scale_rule {
      name                = "http-scaler"
      concurrent_requests = "50"
    }
  }
}

# ---------------------------------------------------------------------------
# Container App — frontend
# ---------------------------------------------------------------------------
resource "azurerm_container_app" "frontend" {
  name                         = "${local.name}-frontend"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.this.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  ingress {
    external_enabled = true
    target_port      = 80
    transport        = "http"
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 5

    container {
      name   = "frontend"
      image  = "${azurerm_container_registry.this.login_server}/enterprisecore-frontend:${var.frontend_image_tag}"
      cpu    = 0.25
      memory = "0.5Gi"
    }
  }
}
