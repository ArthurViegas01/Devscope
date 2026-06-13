"""
ASGI entrypoint. Composes:
  - FastAPI app (host) with /health and / routes, CORS, lifespan-managed services
  - FastMCP server mounted under / via streamable HTTP transport (routes /mcp internally)
  - RateLimitMiddleware applied to all requests as a pure ASGI wrapper
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis_async
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP

from devscope.config import Settings, get_settings
from devscope.logging_config import configure_logging, get_logger
from devscope.middleware import BearerAuthMiddleware, RateLimitMiddleware
from devscope.services import GitHubClient, LLMBudget, LLMService, ProfileAnalyzer
from devscope.services.cache_service import CacheService
from devscope.tools import Services, register_tools

log = get_logger(__name__)


def _build_mcp(services: Services, settings: Settings) -> FastMCP:
    mcp = FastMCP(
        name="devscope",
        instructions=(
            "GitHub Portfolio Intel - tools to analyse public GitHub profiles, "
            "evaluate single repositories, cross-check skills against job "
            "descriptions, and generate streamed recruiter summaries."
        ),
        host=settings.mcp_host,
        port=settings.mcp_port,
    )
    register_tools(mcp, services)
    return mcp


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Wire up Redis, services, and FastMCP on startup; tear down on shutdown."""
    settings: Settings = app.state.settings
    redis_client: redis_async.Redis = app.state.redis
    github: GitHubClient = app.state.github
    mcp_session_manager = app.state.mcp_session_manager

    configure_logging()
    log.info(
        "server.startup",
        env=settings.environment,
        region=settings.deploy_region,
        model=settings.groq_model,
    )

    # Fail open: a Redis outage (or an unreachable REDIS_URL) must not take the
    # whole server down at boot. Bound the probe with a timeout so a hanging
    # TCP connect can't block uvicorn from ever accepting traffic (the cause of
    # a "running but 502" deploy). Caching + rate-limiting already tolerate
    # Redis errors; /health reports "degraded" in this state.
    try:
        await asyncio.wait_for(redis_client.ping(), timeout=5.0)
    except Exception:  # noqa: BLE001
        log.warning("server.redis_unavailable_at_startup")

    async with mcp_session_manager.run():
        try:
            yield
        finally:
            log.info("server.shutdown")
            await github.aclose()
            await redis_client.aclose()


def create_app() -> FastAPI:
    settings = get_settings()

    redis_client = redis_async.from_url(
        str(settings.redis_url), encoding="utf-8", decode_responses=False
    )
    cache = CacheService(redis_client)
    github = GitHubClient(settings, cache)
    analyzer = ProfileAnalyzer()
    llm = LLMService(settings)
    budget = LLMBudget(redis_client, settings.llm_daily_budget)
    services = Services(github=github, analyzer=analyzer, llm=llm, budget=budget)

    app = FastAPI(
        title="Devscope MCP",
        version="0.1.0",
        description="GitHub Portfolio Intel - MCP server",
        lifespan=lifespan,
        redirect_slashes=False,
    )

    mcp = _build_mcp(services, settings)
    mcp_asgi = mcp.streamable_http_app()

    app.state.settings = settings
    app.state.redis = redis_client
    app.state.github = github
    app.state.mcp_session_manager = mcp.session_manager

    # Define FastAPI routes BEFORE mounting the catch-all sub-app so that
    # Starlette matches /health and / against these routes first.
    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        """Liveness and readiness probe. Checks Redis connectivity."""
        s: Settings = app.state.settings
        redis_ok = False
        try:
            await app.state.redis.ping()
            redis_ok = True
        except Exception:  # noqa: BLE001, S110
            pass
        return {
            "status": "ok" if redis_ok else "degraded",
            "environment": s.environment,
            "region": s.deploy_region,
            "model": s.groq_model,
            "redis": "ok" if redis_ok else "down",
            "version": "0.1.0",
        }

    @app.get("/", tags=["meta"])
    async def root() -> dict:
        return {
            "service": "devscope",
            "mcp_endpoint": "/mcp",
            "docs": "/docs",
            "health": "/health",
        }

    # Wrap the MCP sub-app with bearer auth before mounting.
    # FastAPI routes (/health, /) are already registered above and matched first
    # by Starlette, so they remain public. Only requests that fall through to
    # the mount (i.e., /mcp) are subject to auth.
    mcp_asgi_authed = BearerAuthMiddleware(
        mcp_asgi, token=settings.mcp_auth_token.get_secret_value()
    )
    app.mount("/", mcp_asgi_authed)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        # The MCP streamable-HTTP transport reads the session id from this
        # response header; cross-origin it stays hidden from JS unless exposed.
        expose_headers=["mcp-session-id"],
    )

    app.add_middleware(
        RateLimitMiddleware,
        redis_client=redis_client,
        per_minute=settings.rate_limit_per_minute,
        proxy_depth=settings.trusted_proxy_depth,
    )

    return app


app = create_app()


def run() -> None:
    """Console-script entrypoint: devscope."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "devscope.server:app",
        host=settings.mcp_host,
        port=settings.mcp_port,
        log_level=settings.log_level.lower(),
        reload=not settings.is_production,
    )


if __name__ == "__main__":
    run()
