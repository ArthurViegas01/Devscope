# devscope

GitHub portfolio intelligence via MCP. Exposes structured analysis tools to Claude and other LLM clients - profile analysis, repository evaluation, job matching, and recruiter summaries.

[![backend-ci](https://github.com/ArthurViegas01/devscope/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/ArthurViegas01/devscope/actions/workflows/backend-ci.yml)
[![frontend-ci](https://github.com/ArthurViegas01/devscope/actions/workflows/frontend-ci.yml/badge.svg)](https://github.com/ArthurViegas01/devscope/actions/workflows/frontend-ci.yml)
[![infra-plan](https://github.com/ArthurViegas01/devscope/actions/workflows/infra-plan.yml/badge.svg)](https://github.com/ArthurViegas01/devscope/actions/workflows/infra-plan.yml)

## What it does

The Model Context Protocol (MCP) lets AI agents call structured tools exposed by an external server. devscope implements that protocol with FastMCP, registering four tools any compliant client (Claude Desktop, Cursor, Continue, or the bundled React UI) can invoke by name.

| Tool | Input | Returns |
|------|-------|---------|
| `analyze_profile` | `username` | Top languages by %, total stars, most-starred repos, recent activity |
| `evaluate_repository` | `repo_url` | Languages, README excerpt, architecture signals, has_tests/ci/dockerfile |
| `map_to_job` | `username`, `job_description` | Match score, matched/missing skills, strengths, gaps |
| `generate_recruiter_summary` | `username` | Streamed Markdown recruiter report, tokens emitted as MCP progress events |

## Architecture

```
MCP client (Claude Desktop / IDE agent / web UI)
    |
    |  JSON-RPC over Streamable HTTP
    v
FastMCP  (/mcp)
    |
    +-- Tool dispatcher
    |       +-- GitHub REST API v3  (httpx, up to 500 repos via pagination)
    |       +-- LangChain + Groq    (map_to_job, generate_recruiter_summary)
    |       +-- ProfileAnalyzer     (pure Python aggregation)
    |
    +-- Upstash Redis
            +-- Response cache      (TTL 1 hour, namespaced devscope:gh:*)
            +-- Rate limiter        (fixed window, 30 req/min per IP)
```

FastMCP mounts as an ASGI sub-app under FastAPI. Rate limiting runs as a pure ASGI middleware (not BaseHTTPMiddleware) so it is compatible with the SSE streaming transport and covers the MCP endpoint without buffering.

## Stack

Python 3.12, FastMCP, FastAPI, GitHub REST API v3, httpx, LangChain, Groq / GPT-OSS-120b, Upstash Redis, Pydantic v2, structlog, Docker, Railway, Netlify, Terraform

## Quick start

```bash
cp backend/.env.example backend/.env
# Set GITHUB_TOKEN and GROQ_API_KEY in backend/.env

docker compose up --build -d     # backend on :8000, Redis on :6379
cd frontend && npm install && npm run dev   # UI on :5173
```

## Connect to Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "devscope": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Config location: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows).

For any other MCP client, point it at `http://localhost:8000/mcp` using the Streamable HTTP transport.

```bash
# Test with MCP Inspector
npx @modelcontextprotocol/inspector http://localhost:8000/mcp
```

## Deploy

See [docs/DEPLOY.md](docs/DEPLOY.md) for the full guide covering Railway, Upstash, Netlify, Terraform state setup, GitHub Actions secrets, and rollback procedures.

## Security

The `/mcp` endpoint is public on the internet and two tools spend a paid LLM plus a shared GitHub PAT, so the hardening focuses on access control and cost abuse.

**Authentication.** A pure ASGI `BearerAuthMiddleware` wraps the MCP sub-app: every `/mcp` request must send `Authorization: Bearer <MCP_AUTH_TOKEN>`, compared in constant time (`hmac.compare_digest`). `/health` and `/` stay public. `MCP_AUTH_TOKEN` has no default, so the service fails fast if it is unset.

**LLM cost control.** A daily Redis counter (fail-closed) caps combined `map_to_job` + `generate_recruiter_summary` calls at `LLM_DAILY_BUDGET`. `job_description` is rejected above 12,000 characters before the prompt is built.

**GitHub quota protection.** An hourly Redis budget guards the shared PAT, pagination is capped at `MAX_PAGES=2` (200 repos/request), and a low-remaining alarm fires when `X-RateLimit-Remaining < 500`.

**SSRF / path-traversal.** `evaluate_repository` validates `owner` and `repo` against strict allowlists and explicitly rejects `.` and `..` (with `quote()` as defence in depth) so a crafted `repo_url` cannot pivot the server's PAT onto arbitrary GitHub API paths.

**Rate limiting.** Fixed window of 30 req/min per IP. On a Redis error the middleware fails closed to an in-memory window instead of failing open.

**Prompt injection.** Untrusted bio/description/`job_description` text is stripped of control chars, truncated, and wrapped in `[BEGIN.../END...]` fences; both system prompts instruct the model to treat fenced blocks as data, never instructions.

**Transport and disclosure.** `netlify.toml` sends CSP, HSTS, and frame-ancestors on the frontend. GitHub and LLM errors are logged internally and returned to clients as generic messages. In production `/health` returns only a status, `/` omits the MCP endpoint, and `/docs` / `/openapi.json` are disabled. The container runs as a non-root user and CORS uses an explicit non-wildcard origin list.

**Production checklist.** Set `MCP_AUTH_TOKEN` (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) and `REDIS_PASSWORD` in the platform env, and set a monthly spend cap in the Groq console as an independent second barrier.

## Key decisions

**FastMCP over raw SDK.** FastMCP handles session management, request routing, and transport negotiation. The decorator API keeps tool registration close to the logic and lets Pydantic v2 models serve directly as return types.

**Pure ASGI middleware for rate limiting.** `BaseHTTPMiddleware` buffers the entire response before sending, which breaks SSE streams. A pure ASGI middleware passes `scope/receive/send` through directly and only intercepts the request phase.

**Fail-open Redis.** Cache errors are caught and logged at WARNING; requests fall through to the GitHub API. A Redis outage degrades performance but does not take the service down.

**1-hour Redis TTL.** Public GitHub portfolio data (repos, languages, stars) does not change minute-to-minute. A 1-hour TTL keeps the server well under GitHub's 5,000 req/hour rate limit even under repeated calls across clients.

**Railway over Fly.io or Render.** Railway deploys arbitrary Docker images with zero config drift between local and production, has a functional free tier for this scale, and integrates cleanly with the Terraform provider.

## License

MIT
