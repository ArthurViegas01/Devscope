# devscope - Deploy Guide

This document covers everything you need to go from zero to a running production deployment: Railway (backend), Upstash (Redis), Netlify (frontend), Terraform, and CI/CD.

> **Status (2026-07-21): Terraform is disabled.** The live stack is currently provisioned and managed **manually** via the Railway, Netlify, and Upstash dashboards. The Terraform config has no remote state and does not track those resources, so `terraform apply` would create duplicates and must NOT be run yet. The Terraform sections below describe the target IaC setup; follow them only when you are ready to configure a remote backend and import the existing resources. Day-to-day changes for now are made directly in each provider's dashboard.

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Terraform | >= 1.6 | `brew install terraform` or [releases](https://releases.hashicorp.com/terraform/) |
| Docker | >= 25 | Required for local dev; CI builds and pushes the image |
| Node.js | >= 20 | Frontend build |
| Python | 3.12 | Backend local dev |
| `gh` CLI | >= 2 | For setting GitHub Actions secrets |

You need accounts on:

- [Railway](https://railway.app) (backend host)
- [Upstash](https://upstash.com) (serverless Redis)
- [Netlify](https://netlify.com) (frontend host)
- [Groq](https://console.groq.com) (LLM API)
- [GitHub](https://github.com) (image registry via GHCR, source of truth)

---

## 1. Terraform remote state (required before first apply)

The Terraform configuration ships without a remote backend. Local state will be lost after CI runs. Configure one before provisioning anything.

**Option A: Terraform Cloud (easiest)**

```hcl
# terraform/main.tf - add this block at the top
terraform {
  cloud {
    organization = "your-org"
    workspaces {
      name = "devscope-prod"
    }
  }
}
```

Then run `terraform login` locally.

**Option B: AWS S3 + DynamoDB**

```hcl
terraform {
  backend "s3" {
    bucket         = "your-tfstate-bucket"
    key            = "devscope/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
```

After adding the backend block, run `terraform init` to migrate state.

---

## 2. Upstash Redis

1. Log in to [console.upstash.com](https://console.upstash.com).
2. Create a new database: region `us-east-1`, type `Regional`, TLS enabled.
3. Copy the **Redis URL** (starts with `rediss://`). Format: `rediss://default:<token>@us1-xxx.upstash.io:6379`.

Keep this URL - you will pass it as `TF_VAR_upstash_redis_url`.

---

## 3. API tokens

Gather all secrets before running Terraform:

```bash
# Railway: dashboard.railway.app -> account -> API Keys -> New Token
export TF_VAR_railway_token="your-railway-token"

# Netlify: app.netlify.com -> User settings -> Applications -> New access token
export TF_VAR_netlify_token="your-netlify-token"

# GitHub: github.com -> Settings -> Developer settings -> Personal access tokens
# Scopes needed: read:packages, write:packages, read:org
export TF_VAR_github_token="ghp_..."

# Groq: console.groq.com -> API Keys -> Create new key
export TF_VAR_groq_api_key="gsk_..."

# Upstash Redis URL from step 2
export TF_VAR_upstash_redis_url="rediss://default:<token>@us1-xxx.upstash.io:6379"
```

Tip: put these in a `.envrc` file (git-ignored) and use `direnv` to load them automatically.

---

## 4. First-time provisioning

```bash
cd terraform
terraform init
terraform plan   # review what will be created
terraform apply
```

Terraform creates:
- A Railway project with the backend service, env vars, and domain
- A Netlify site with the `VITE_MCP_SERVER_URL` env var pointed at Railway

After `apply` completes, note the outputs:

```bash
terraform output backend_public_url   # e.g. https://devscope-mcp-production.up.railway.app
terraform output frontend_url         # e.g. https://devscope.netlify.app
```

---

## 5. GitHub Actions secrets

The `backend-build-push` workflow logs in to GHCR with the **automatic** `GITHUB_TOKEN` (no secret to set). You only need to add secrets for the optional Railway redeploy trigger and for the `infra-apply` workflow.

For the automatic image-push → Railway-redeploy loop (`backend-build-push.yml`):

```bash
gh secret set RAILWAY_TOKEN          --body "$TF_VAR_railway_token"
gh secret set RAILWAY_SERVICE_ID     --body "your-railway-service-id"
gh secret set RAILWAY_ENVIRONMENT_ID --body "your-railway-environment-id"
```

If `RAILWAY_TOKEN`/`RAILWAY_SERVICE_ID` are absent, the build still pushes the image; only the auto-redeploy step is skipped (Railway also redeploys on its own when the `latest` tag moves).

For running `terraform apply` from the Actions tab (`infra-apply.yml`):

```bash
gh secret set NETLIFY_TOKEN          --body "$TF_VAR_netlify_token"
gh secret set NETLIFY_SITE_ID        --body "$TF_VAR_netlify_site_id"
gh secret set GITHUB_PAT_FOR_BACKEND --body "$TF_VAR_github_token"
gh secret set GROQ_API_KEY           --body "$TF_VAR_groq_api_key"
gh secret set UPSTASH_REDIS_URL      --body "$TF_VAR_upstash_redis_url"
# RAILWAY_TOKEN is reused from above
```

The `backend-build-push` workflow triggers on every push to `main` that touches `backend/**`, builds the Docker image, and pushes to `ghcr.io/<owner>/devscope-backend:latest`.

### Make the GHCR package public (required)

The pushed image inherits the repository's visibility. If the repo is private, the image package is **private**, and Railway cannot pull it (this Terraform config does not set registry credentials on the Railway service). After the first successful push:

1. Go to `https://github.com/users/<owner>/packages/container/devscope-backend/settings`
2. Under **Danger Zone → Change visibility**, set it to **Public**.

Alternatively, keep it private and add registry credentials to the Railway service in the Railway dashboard (Service → Settings → Source → private registry).

---

## 6. Connecting Claude Desktop

Once the backend is live, add this to your Claude Desktop config:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "devscope": {
      "url": "https://your-backend.up.railway.app/mcp"
    }
  }
}
```

Replace the URL with your actual Railway backend URL (from `terraform output backend_public_url`, without the trailing `/mcp` - Terraform already appends it).

Restart Claude Desktop. The four tools (`analyze_profile`, `evaluate_repository`, `map_to_job`, `generate_recruiter_summary`) will appear in the tool picker.

---

## 7. Connecting other MCP clients

Any client that supports the Streamable HTTP MCP transport works. Point it at:

```
https://your-backend.up.railway.app/mcp
```

**MCP Inspector (for testing):**

```bash
npx @modelcontextprotocol/inspector https://your-backend.up.railway.app/mcp
```

---

## 8. Local development

```bash
# Backend + Redis via Docker Compose
cp backend/.env.example backend/.env
# Edit backend/.env: set GITHUB_TOKEN and GROQ_API_KEY at minimum

docker compose up --build -d
# Backend: http://localhost:8000
# Health check: http://localhost:8000/health

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
# UI: http://localhost:5173
```

The dev compose service mounts `backend/src` as a volume so Python source changes hot-reload without a rebuild. The Vite dev server proxies `/mcp` to `localhost:8000/mcp` so the frontend works without CORS config.

---

## 9. Continuous deployment flow

```
git push origin main
    |
    +-- backend-ci.yml         (pytest, ruff, mypy - blocks merge if red)
    +-- frontend-ci.yml        (tsc --noEmit, vite build - blocks merge if red)
    +-- infra-plan.yml         (terraform plan - shows diff in PR comments)
    |
    +-- backend-build-push.yml (builds Docker image, pushes to GHCR)
    |
    Railway detects new image -> redeploys backend
    Netlify detects push      -> rebuilds and redeploys frontend
```

`infra-plan` only runs `plan`, never `apply`. Infrastructure changes go through a manual `terraform apply` after reviewing the plan output. This is intentional - automatic apply on push is risky for stateful resources.

---

## 10. Environment variables reference

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `GITHUB_TOKEN` | Yes | - | GitHub PAT with `public_repo` read scope |
| `GROQ_API_KEY` | Yes | - | Groq console API key |
| `REDIS_URL` | Yes | - | Full `rediss://` Upstash URL with token (the app reads `REDIS_URL`; Terraform sets it from `TF_VAR_upstash_redis_url`) |
| `CORS_ORIGINS` | Yes (prod) | `http://localhost:5173` | Comma-separated list of allowed origins |
| `GROQ_MODEL` | No | `openai/gpt-oss-120b` | Groq model ID |
| `RATE_LIMIT_PER_MINUTE` | No | `30` | Requests per IP per minute |
| `TRUSTED_PROXY_DEPTH` | No | `1` | Number of proxies in front of the backend (Railway = 1) |
| `ENVIRONMENT` | No | `development` | `production` enables JSON structlog output |
| `LOG_LEVEL` | No | `INFO` | Python log level |
| `PORT` | No | `8000` | Injected by Railway automatically |

---

## 11. Rollback

**Backend:** Railway keeps the last N deploys. From the Railway dashboard, open the service, go to Deployments, and click Rollback on any previous entry.

Via CLI (if you have the Railway CLI installed):

```bash
railway rollback
```

**Frontend:** Netlify keeps all deploys. From the Netlify dashboard, open the site, go to Deploys, click any previous deploy, then "Publish deploy."

**Infrastructure:** Terraform state tracks the last applied config. To revert an infrastructure change, check out the previous version of the Terraform files and run `terraform apply` again.

---

## 12. Monitoring and troubleshooting

**Health endpoint:**

```bash
curl https://your-backend.up.railway.app/health
# Returns: {"status": "ok", "environment": "production", "redis": "ok", ...}
```

`redis: "down"` means Upstash is unreachable but the backend is still serving (fail-open design). The GitHub API calls will still work; only caching is degraded.

**Logs:**

```bash
# Railway - from the dashboard or:
railway logs --service devscope-backend

# Local Docker:
docker compose logs -f backend
```

**Rate limit errors:** 429 responses mean the client IP hit 30 req/min. The `X-RateLimit-Remaining` and `X-RateLimit-Reset` headers are included in every response.

**CORS errors in browser:** The backend CORS origin list is set from `CORS_ORIGINS`. If your frontend URL is not in that list, add it in Railway env vars or via `terraform apply` after updating `terraform/main.tf`.
