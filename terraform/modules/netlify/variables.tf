# =============================================================================
# modules/netlify/variables.tf
# =============================================================================

variable "site_id" {
  description = "Netlify site ID. Found at: Netlify UI -> Site -> Site configuration -> Site ID."
  type        = string
}

variable "site_name" {
  description = "Netlify site subdomain (e.g. 'devscope' -> devscope.netlify.app). Used for output URLs only."
  type        = string
}

variable "custom_domain" {
  description = "Optional custom domain. Empty string = use Netlify default."
  type        = string
  default     = ""
}

variable "backend_public_url" {
  description = "Public /mcp URL of the backend. Injected as MCP_BACKEND_URL, consumed server-side by the proxy function (not exposed to the browser)."
  type        = string
}

variable "mcp_auth_token" {
  description = "Bearer token the proxy function injects when forwarding to the backend. Must match the backend's MCP_AUTH_TOKEN."
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Logical environment name (production, staging)."
  type        = string
}
