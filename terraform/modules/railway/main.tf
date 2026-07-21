# =============================================================================
# modules/railway/main.tf
# =============================================================================

terraform {
  required_providers {
    railway = {
      source = "terraform-community-providers/railway"
    }
  }
}

resource "railway_project" "this" {
  name        = var.project_name
  description = "GitHub Portfolio Intel - MCP server (region: ${var.region})"
  private     = false
}

resource "railway_environment" "production" {
  name       = "production"
  project_id = railway_project.this.id
}

resource "railway_service" "backend" {
  name         = "backend"
  project_id   = railway_project.this.id
  source_image = var.backend_image
}

resource "railway_service_domain" "backend" {
  environment_id = railway_environment.production.id
  service_id     = railway_service.backend.id
  subdomain      = var.backend_subdomain
}

locals {
  backend_env = {
    MCP_HOST              = "0.0.0.0"
    MCP_PORT              = "8000"
    ENVIRONMENT           = "production"
    LOG_LEVEL             = var.log_level
    MCP_AUTH_TOKEN        = var.mcp_auth_token
    GITHUB_TOKEN          = var.github_token
    GROQ_API_KEY          = var.groq_api_key
    GROQ_MODEL            = var.groq_model
    REDIS_URL             = var.upstash_redis_url
    RATE_LIMIT_PER_MINUTE = tostring(var.rate_limit_per_minute)
    DEPLOY_REGION         = var.region
    CORS_ORIGINS          = var.cors_origins
    TRUSTED_PROXY_DEPTH   = "1"
  }
}

resource "railway_variable" "backend" {
  for_each = local.backend_env

  name           = each.key
  value          = each.value
  service_id     = railway_service.backend.id
  environment_id = railway_environment.production.id
}
