"""
Centralised configuration via Pydantic Settings.

All secrets come from environment variables. The app refuses to start if any
required secret is missing - fail-fast over silent misconfig.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    environment: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    deploy_region: str = "local"

    # Server
    mcp_host: str = "0.0.0.0"  # noqa: S104
    mcp_port: int = 8000

    # Auth
    mcp_auth_token: SecretStr = Field(..., description="Static bearer token for the /mcp endpoint")

    # Integrations
    github_token: SecretStr = Field(..., description="GitHub PAT")
    github_api_base: str = "https://api.github.com"

    groq_api_key: SecretStr = Field(..., description="Groq API key")
    groq_model: str = "llama-3.3-70b-versatile"

    # Redis
    redis_url: RedisDsn = Field(..., description="Redis connection URL")
    cache_ttl_seconds: int = 3600

    # LLM spend control
    llm_daily_budget: int = Field(1000, description="Max LLM calls per calendar day")

    # Rate limiting
    rate_limit_per_minute: int = 30
    trusted_proxy_depth: int = Field(
        1,
        description=(
            "Number of trusted reverse proxy hops in X-Forwarded-For. "
            "Set to 1 when behind Railway or any single load balancer."
        ),
    )

    # CORS
    # NoDecode stops pydantic-settings from JSON-decoding the env var at the
    # source level (which crashed the app when CORS_ORIGINS was a plain CSV
    # string). The before-validator below now owns parsing and accepts both a
    # CSV string and a JSON array string.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            # Tolerate a JSON array string too, so either format works.
            if s.startswith("["):
                try:
                    return json.loads(s)
                except json.JSONDecodeError:
                    pass
            return [item.strip() for item in s.split(",") if item.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
