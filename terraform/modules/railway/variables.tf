# =============================================================================
# modules/railway/variables.tf
# =============================================================================

variable "project_name" {
  description = "Railway project name (already prefixed with environment by the caller)."
  type        = string
}

variable "region" {
  description = "Railway region. MUST be a US region - caller validates this."
  type        = string

  validation {
    condition     = contains(["us-west1", "us-west2", "us-east4"], var.region)
    error_message = "Railway region must be one of: us-west1, us-west2, us-east4. South American regions are forbidden."
  }
}

variable "backend_image" {
  description = "Container image for the FastMCP backend."
  type        = string
}

variable "backend_cpu" {
  description = "vCPU allocation."
  type        = number
}

variable "backend_memory_mb" {
  description = "Memory in MB."
  type        = number
}

variable "backend_replicas" {
  description = "Replica count."
  type        = number
}

variable "github_token" {
  type      = string
  sensitive = true
}

variable "groq_api_key" {
  type      = string
  sensitive = true
}

variable "groq_model" {
  description = "Groq model id used by the LLM service."
  type        = string
  default     = "openai/gpt-oss-120b"
}

variable "mcp_auth_token" {
  description = "Static bearer token the backend requires on /mcp. Required for boot."
  type        = string
  sensitive   = true
}

variable "upstash_redis_url" {
  description = "rediss:// connection URL from Upstash (cache + rate limiter)."
  type        = string
  sensitive   = true
}

variable "rate_limit_per_minute" {
  type    = number
  default = 30
}

variable "log_level" {
  type    = string
  default = "INFO"
}

variable "backend_subdomain" {
  type        = string
  description = "Subdomain for the backend Railway service."
}

variable "cors_origins" {
  description = "Comma-separated list of allowed CORS origins (the Netlify frontend URL)."
  type        = string
  default     = ""
}