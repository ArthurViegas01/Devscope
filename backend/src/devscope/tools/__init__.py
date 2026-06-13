"""
MCP tool registration.

register_tools(mcp, services) is called once at server startup. Each tool is
a thin adapter: validate input, call service layer, return a Pydantic model.
"""

from __future__ import annotations

from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from devscope.services import GitHubClient, LLMBudget, LLMService, ProfileAnalyzer
from devscope.tools.analyze_profile import register as register_analyze_profile
from devscope.tools.evaluate_repository import register as register_evaluate_repo
from devscope.tools.generate_recruiter_summary import (
    register as register_generate_summary,
)
from devscope.tools.map_to_job import register as register_map_to_job


@dataclass
class Services:
    github: GitHubClient
    analyzer: ProfileAnalyzer
    llm: LLMService
    budget: LLMBudget


def register_tools(mcp: FastMCP, services: Services) -> None:
    register_analyze_profile(mcp, services.github, services.analyzer)
    register_evaluate_repo(mcp, services.github)
    register_map_to_job(mcp, services.github, services.analyzer, services.llm, services.budget)
    register_generate_summary(mcp, services.github, services.analyzer, services.llm, services.budget)
