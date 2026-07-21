# =============================================================================
# variables.tf - Infrastructure inputs for Devscope
#
# REGION POLICY (enforced via validation blocks below):
#   Sao Paulo (gru / sa-* / southamerica-*) is REJECTED at plan time.
#   Allowed Railway regions (US only):
#     us-west1   Pacific Northwest
#     us-west2   California
#     us-east4   Virginia  (default)
# =============================================================================

variable "project_name" {
  description = "Logical project name used as a prefix for resources."
  type        = string
  default     = "devscope"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,30}$", var.project_name))
    error_message = "project_name must be lowercase, start with a letter, and contain only [a-z0-9-]."
  }
}

variable "environment" {
  description = "Deployment environment (production, staging)."
  type        = string
  default     = "production"

  validation {
    condition     = contains(["production", "staging"], var.environment)
    error_message = "environment must be one of: production, staging."
  }
}

variable "railway_region" {
  description = "Railway region. Must be a US region. Sao Paulo (gru) is forbidden."
  type        = string
  default     = "us-east4"

  validation {
    condition     = contains(["us-west1", "us-west2", "us-east4"], var.railway_region)
    error_message = "railway_region must be one of: us-west1, us-west2, us-east4."
  }

  validation {
    condition     = !can(regex("(?i)(gru|sa-|sao|southamerica|brazil|br-)", var.railway_region))
    error_message = "South American / Sao Paulo regions are forbidden by project policy."
  }
}

# Secrets - set via TF_VAR_* environment variables, never in committed files.

variable "railway_token" {
  description = "Railway API token. Set via TF_VAR_railway_token."
  type        = string
  sensitive   = true
}

variable "netlify_token" {
  description = "Netlify Personal Access Token. Set via TF_VAR_netlify_token."
  type        = string
  sensitive   = true
}

variable "github_token" {
  description = "GitHub PAT consumed by the MCP backend."
  type        = string
  sensitive   = true

  validation {
    condition     = var.github_token == "" || length(var.github_token) >= 20
    error_message = "github_token looks too short to be a valid PAT."
  }
}

variable "groq_api_key" {
  description = "Groq API key used by the LLM service."
  type        = string
  sensitive   = true

  validation {
    condition     = var.groq_api_key == "" || length(var.groq_api_key) >= 20
    error_message = "groq_api_key looks too short."
  }
}

variable "groq_model" {
  description = "Groq model id used by the LLM service."
  type        = string
  default     = "openai/gpt-oss-120b"
}

variable "mcp_auth_token" {
  description = "Static bearer token guarding /mcp. The SAME value is used by the backend to validate and by the Netlify proxy function to sign requests. Set via TF_VAR_mcp_auth_token."
  type        = string
  sensitive   = true
  default     = ""

  validation {
    condition     = var.mcp_auth_token == "" || length(var.mcp_auth_token) >= 20
    error_message = "mcp_auth_token looks too short to be a secure token."
  }
}

variable "upstash_redis_url" {
  description = "Upstash Redis URL (rediss://default:<token>@<host>:<port>)."
  type        = string
  sensitive   = true

  validation {
    condition     = var.upstash_redis_url == "" || can(regex("^rediss?://", var.upstash_redis_url))
    error_message = "upstash_redis_url must start with redis:// or rediss://"
  }
}

# Backend (Railway)

variable "backend_image" {
  description = "Container image for the FastMCP backend."
  type        = string
  default     = "ghcr.io/ArthurViegas01/devscope-backend:latest"
}

variable "backend_cpu" {
  description = "vCPU allocation for the backend service."
  type        = number
  default     = 1
}

variable "backend_memory_mb" {
  description = "Memory allocation for the backend service in MB."
  type        = number
  default     = 512

  validation {
    condition     = var.backend_memory_mb >= 256 && var.backend_memory_mb <= 8192
    error_message = "backend_memory_mb must be between 256 and 8192."
  }
}

variable "backend_replicas" {
  description = "Number of backend replicas."
  type        = number
  default     = 1
}

variable "rate_limit_per_minute" {
  description = "Per-IP request rate limit applied by the middleware."
  type        = number
  default     = 30
}

# Frontend (Netlify)

variable "netlify_site_id" {
  description = "Netlify site ID. Netlify UI -> Site -> Site configuration -> Site ID."
  type        = string
  sensitive   = true
  default     = "00000000-0000-0000-0000-000000000000"
}

variable "netlify_site_name" {
  description = "Netlify site subdomain (e.g. 'devscope' -> devscope.netlify.app)."
  type        = string
  default     = "devscope"
}

variable "frontend_custom_domain" {
  description = "Optional custom domain for the frontend. Empty = use Netlify default."
  type        = string
  default     = ""
}

variable "log_level" {
  description = "Log level for the backend."
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR"], var.log_level)
    error_message = "log_level must be one of: DEBUG, INFO, WARNING, ERROR."
  }
}
