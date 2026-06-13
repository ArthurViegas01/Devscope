"""
Async GitHub REST API client with Redis-backed caching.

Cache keys:
  gh:user:{username}        TTL = settings.cache_ttl_seconds
  gh:repos:{username}       TTL = settings.cache_ttl_seconds
  gh:repo:{owner}/{repo}    TTL = settings.cache_ttl_seconds
  gh:lang:{owner}/{repo}    TTL = settings.cache_ttl_seconds
  gh:readme:{owner}/{repo}  TTL = settings.cache_ttl_seconds
  gh:tree:{owner}/{repo}    TTL = settings.cache_ttl_seconds
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

import httpx

from devscope.config import Settings
from devscope.logging_config import get_logger
from devscope.models.github import GitHubRepo, GitHubUser
from devscope.services.cache_service import CacheService

log = get_logger(__name__)

PER_PAGE = 100
MAX_PAGES = 2  # reduced from 5 to limit PAT usage per request (200 repos max)
_GH_RATELIMIT_WARN = 500  # warn when X-RateLimit-Remaining drops below this


class GitHubAPIError(RuntimeError):
    """Raised on non-recoverable GitHub API errors (auth, 404, rate-limit, etc.)."""


class GitHubClient:
    def __init__(self, settings: Settings, cache: CacheService) -> None:
        self._settings = settings
        self._cache = cache
        self._http = httpx.AsyncClient(
            base_url=settings.github_api_base,
            headers={
                "Authorization": f"Bearer {settings.github_token.get_secret_value()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "devscope/0.1",
            },
            timeout=httpx.Timeout(15.0, connect=5.0),
            http2=False,
            # GitHub returns 301 for renamed/moved repos (e.g. anthropics/
            # anthropic-cookbook). Without this, the redirect body is fed to the
            # model and fails validation. Same-host redirects keep the auth header.
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _check_gh_budget(self) -> None:
        """Increment hourly call counter. Raises GitHubAPIError when budget exceeded."""
        hour = datetime.now(UTC).strftime("%Y-%m-%dT%H")
        key = f"gh:budget:{hour}"
        try:
            n = await self._cache.client.incr(key)
            if n == 1:
                await self._cache.client.expire(key, 3600)
            if n > self._settings.github_hourly_budget:
                log.warning("gh.budget_exceeded", count=n, cap=self._settings.github_hourly_budget)
                raise GitHubAPIError(
                    "GitHub API hourly budget exceeded. Please try again in a few minutes."
                )
        except GitHubAPIError:
            raise
        except Exception:  # noqa: BLE001
            log.warning("gh_budget.redis_error")

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        await self._check_gh_budget()
        try:
            resp = await self._http.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise GitHubAPIError(f"GitHub API timeout: {path}") from exc

        remaining = resp.headers.get("x-ratelimit-remaining")
        if remaining is not None:
            try:
                if int(remaining) < _GH_RATELIMIT_WARN:
                    log.warning("gh.ratelimit_low", remaining=int(remaining), path=path)
            except ValueError:
                pass

        if resp.status_code == 404:
            raise GitHubAPIError("Profile or repository not found.")
        if resp.status_code in (403, 429) or (
            resp.status_code == 403 and "rate limit" in resp.text.lower()
        ):
            log.warning("gh.api_error", status=resp.status_code, path=path, detail=resp.text[:200])
            raise GitHubAPIError(
                "GitHub API limit reached. Please try again in a few minutes."
            )
        if resp.status_code >= 400:
            log.warning("gh.api_error", status=resp.status_code, path=path, detail=resp.text[:200])
            raise GitHubAPIError("Error querying the GitHub API.")
        return resp.json()

    async def _get_cached(self, cache_key: str, path: str, params: dict | None = None) -> Any:
        cached = await self._cache.get_json(cache_key)
        if cached is not None:
            log.debug("github.cache_hit", key=cache_key)
            return cached
        data = await self._get(path, params)
        await self._cache.set_json(cache_key, data, self._settings.cache_ttl_seconds)
        log.debug("github.cache_miss", key=cache_key)
        return data

    async def get_user(self, username: str) -> GitHubUser:
        data = await self._get_cached(f"gh:user:{username}", f"/users/{username}")
        return GitHubUser.model_validate(data)

    async def list_user_repos(self, username: str) -> list[GitHubRepo]:
        cache_key = f"gh:repos:{username}"
        cached = await self._cache.get_json(cache_key)
        if cached is not None:
            return [GitHubRepo.model_validate(r) for r in cached]

        all_repos: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            batch = await self._get(
                f"/users/{username}/repos",
                params={"per_page": PER_PAGE, "page": page, "sort": "pushed"},
            )
            if not batch:
                break
            all_repos.extend(batch)
            if len(batch) < PER_PAGE:
                break

        await self._cache.set_json(cache_key, all_repos, self._settings.cache_ttl_seconds)
        return [GitHubRepo.model_validate(r) for r in all_repos]

    async def get_repo(self, owner: str, repo: str) -> GitHubRepo:
        data = await self._get_cached(f"gh:repo:{owner}/{repo}", f"/repos/{owner}/{repo}")
        return GitHubRepo.model_validate(data)

    async def get_repo_languages(self, owner: str, repo: str) -> dict[str, int]:
        return await self._get_cached(f"gh:lang:{owner}/{repo}", f"/repos/{owner}/{repo}/languages")

    async def get_readme(self, owner: str, repo: str) -> str | None:
        cache_key = f"gh:readme:{owner}/{repo}"
        cached = await self._cache.get_json(cache_key)
        if cached is not None:
            return cached if cached != "" else None
        try:
            data = await self._get(f"/repos/{owner}/{repo}/readme")
        except GitHubAPIError:
            await self._cache.set_json(cache_key, "", self._settings.cache_ttl_seconds)
            return None
        encoded = data.get("content", "")
        try:
            text = base64.b64decode(encoded).decode("utf-8", errors="replace")
        except (ValueError, UnicodeDecodeError):
            text = ""
        await self._cache.set_json(cache_key, text, self._settings.cache_ttl_seconds)
        return text or None

    async def list_repo_root(self, owner: str, repo: str, branch: str = "main") -> list[str]:
        """List filenames at the repo root for architecture signal detection."""
        cache_key = f"gh:tree:{owner}/{repo}"
        cached = await self._cache.get_json(cache_key)
        if cached is not None:
            return cached
        try:
            data = await self._get(f"/repos/{owner}/{repo}/contents", params={"ref": branch})
        except GitHubAPIError:
            return []
        names = [item["name"] for item in data if isinstance(item, dict)]
        await self._cache.set_json(cache_key, names, self._settings.cache_ttl_seconds)
        return names
