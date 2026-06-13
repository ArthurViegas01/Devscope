"""MCP tool: map_to_job(username, job_description). Uses LangChain + Groq."""

from __future__ import annotations

import json

from groq import GroqError
from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from devscope.logging_config import get_logger
from devscope.models.analysis import JobMatchResult, ProfileAnalysis
from devscope.services.github_client import GitHubAPIError, GitHubClient
from devscope.services.llm_budget import LLMBudget
from devscope.services.llm_service import LLMService
from devscope.services.profile_analyzer import ProfileAnalyzer
from devscope.tools.analyze_profile import _validate_username

log = get_logger(__name__)


def _profile_to_text(p: ProfileAnalysis) -> str:
    langs = ", ".join(f"{ls.language} ({ls.percentage}%)" for ls in p.top_languages) or "n/a"
    starred = "; ".join(
        f"{r['name']} ({r.get('stars', 0)} stars, {r.get('language') or 'mixed'})"
        for r in p.most_starred[:5]
    )
    return (
        f"GitHub user: @{p.username}\n"
        f"Name: {p.name or 'unknown'}\n"
        f"Bio: {p.bio or '-'}\n"
        f"Public repos: {p.public_repos}\n"
        f"Total stars: {p.total_stars}\n"
        f"Top languages: {langs}\n"
        f"Most-starred projects: {starred or '-'}\n"
    )


def register(
    mcp: FastMCP,
    github: GitHubClient,
    analyzer: ProfileAnalyzer,
    llm: LLMService,
    budget: LLMBudget,
) -> None:
    @mcp.tool(
        name="map_to_job",
        description=(
            "Cross-reference a GitHub developer's public skills against a job "
            "description. Returns a structured match with an overall score (0-100), "
            "matched skills, missing skills, strengths, and gaps. "
            "Requires a valid GitHub username and at least 30 characters of job text."
        ),
    )
    async def map_to_job(username: str, job_description: str) -> JobMatchResult:
        clean = _validate_username(username)
        if not job_description or len(job_description.strip()) < 30:
            raise ValueError("job_description must be at least 30 characters of meaningful text")

        log.info("tool.map_to_job.start", username=clean)
        try:
            user = await github.get_user(clean)
            repos = await github.list_user_repos(clean)
        except GitHubAPIError as exc:
            raise ValueError(str(exc)) from exc

        profile = analyzer.analyze(user, repos)
        profile_text = _profile_to_text(profile)

        if not await budget.consume():
            raise ValueError("Daily LLM request limit reached. Please try again tomorrow.")

        try:
            raw = await llm.map_to_job_structured(profile_text, job_description.strip())
        except GroqError as exc:
            raise ValueError(f"LLM service error: {exc}") from exc
        except Exception as exc:
            raise ValueError(f"LLM call failed: {exc}") from exc

        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"LLM returned non-JSON: {exc}") from exc

        try:
            return JobMatchResult(username=profile.username, **raw)
        except ValidationError as exc:
            raise ValueError(f"LLM output failed validation: {exc}") from exc
