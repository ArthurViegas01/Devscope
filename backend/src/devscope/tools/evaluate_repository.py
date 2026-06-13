"""MCP tool: evaluate_repository(repo_url)."""

from __future__ import annotations

import re
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP

from devscope.logging_config import get_logger
from devscope.models.analysis import RepositoryEvaluation
from devscope.services.github_client import GitHubAPIError, GitHubClient

log = get_logger(__name__)

# Strict allow-lists: reject dot-segments and anything outside alphanumeric/hyphen.
# _OWNER_RE follows GitHub username/org rules (1-39 chars, no leading/trailing hyphen).
_OWNER_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$")
# _REPO_RE allows dots and underscores as GitHub permits (1-100 chars).
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")

ARCH_SIGNALS: dict[str, str] = {
    "Dockerfile": "containerised",
    "docker-compose.yml": "multi-service local stack",
    "docker-compose.yaml": "multi-service local stack",
    "Makefile": "make-based DX",
    "pyproject.toml": "modern Python packaging",
    "requirements.txt": "pip workflow",
    "package.json": "Node.js project",
    "pnpm-lock.yaml": "pnpm package manager",
    "go.mod": "Go modules",
    "Cargo.toml": "Rust / Cargo",
    "terraform": "Infrastructure as Code (Terraform)",
    ".github": "GitHub-native CI/CD",
    "k8s": "Kubernetes manifests",
    "kubernetes": "Kubernetes manifests",
    "helm": "Helm charts",
    "tests": "tests directory present",
    "test": "tests directory present",
}

REPO_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s#?]+?)(?:\.git)?/?$"
)


def _validate_segment(value: str, pattern: re.Pattern, label: str) -> str:
    """Reject dot-segments and values that don't match the strict allow-list."""
    if value in (".", "..") or not pattern.match(value):
        raise ValueError(f"Invalid {label}: {value!r}")
    return quote(value, safe="")


def _parse_repo_url(url: str) -> tuple[str, str]:
    m = REPO_URL_RE.match(url.strip())
    if not m:
        raise ValueError(f"Not a valid GitHub repo URL: {url!r}")
    owner = _validate_segment(m.group(1), _OWNER_RE, "owner")
    repo = _validate_segment(m.group(2), _REPO_RE, "repo")
    return owner, repo


def register(mcp: FastMCP, github: GitHubClient) -> None:
    @mcp.tool(
        name="evaluate_repository",
        description=(
            "Evaluate a single GitHub repository: primary stack, detected architecture "
            "signals (Dockerfile, CI, IaC, tests), language breakdown, and a README "
            "excerpt. Pass the full repository URL "
            "(e.g. 'https://github.com/owner/repo')."
        ),
    )
    async def evaluate_repository(repo_url: str) -> RepositoryEvaluation:
        owner, name = _parse_repo_url(repo_url)
        log.info("tool.evaluate_repository.start", owner=owner, repo=name)

        try:
            repo = await github.get_repo(owner, name)
            languages = await github.get_repo_languages(owner, name)
            readme = await github.get_readme(owner, name)
            root = await github.list_repo_root(owner, name, branch=repo.default_branch)
        except GitHubAPIError as exc:
            raise ValueError(str(exc)) from exc

        signals = sorted({label for path, label in ARCH_SIGNALS.items() if path in root})
        has_tests = any(p in root for p in ("tests", "test", "__tests__"))
        has_ci = ".github" in root
        has_dockerfile = "Dockerfile" in root or "dockerfile" in root

        excerpt = None
        if readme:
            cleaned = "\n".join(line for line in readme.splitlines() if line.strip())
            excerpt = cleaned[:1500]

        return RepositoryEvaluation(
            owner=owner,
            name=name,
            full_name=repo.full_name,
            description=repo.description,
            primary_language=repo.language,
            languages_breakdown=languages,
            stars=repo.stargazers_count,
            forks=repo.forks_count,
            open_issues=repo.open_issues_count,
            topics=repo.topics,
            has_readme=readme is not None,
            readme_excerpt=excerpt,
            has_tests=has_tests,
            has_ci=has_ci,
            has_dockerfile=has_dockerfile,
            license=None,
            last_pushed=repo.pushed_at,
            architecture_signals=signals,
            url=repo.html_url,
        )
