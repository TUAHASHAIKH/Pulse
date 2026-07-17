"""
Pulse Orchestrator — GitHub Client

Wraps GitHub API calls via httpx. Three responsibilities:
  1. Fetch the diff of a pull request
  2. Fetch the list of changed files with their patches
  3. Post a comment on a pull request with agent findings

Uses direct API calls (not MCP) because:
  - We know exactly which 3 endpoints we need
  - httpx is faster and simpler than running an MCP subprocess
  - MCP is better suited for agents that need to discover/browse repos dynamically

All requests use the GITHUB_TOKEN from config for authentication.
"""

import httpx
from typing import Optional

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger("pulse.github")

# GitHub API base URL
GITHUB_API = "https://api.github.com"


class GitHubClient:
    """
    Async GitHub API client.

    Uses httpx for HTTP requests with proper headers and error handling.
    """

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init the httpx client with proper headers."""
        if self._client is None:
            if not settings.github_token:
                logger.warning(
                    "GITHUB_TOKEN is not configured. "
                    "GitHub API calls will be unauthenticated (rate-limited)."
                )

            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Pulse-DevOps-Agent/0.1.0",
            }
            if settings.github_token:
                headers["Authorization"] = f"Bearer {settings.github_token}"

            self._client = httpx.AsyncClient(
                base_url=GITHUB_API,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def fetch_pr_diff(self, repo: str, pr_number: int) -> str:
        """
        Fetch the full unified diff of a pull request.

        Args:
            repo: Repository full name, e.g. "tuaha/acme-shop"
            pr_number: Pull request number

        Returns:
            The diff as a string in unified diff format.

        Example:
            diff = await github_client.fetch_pr_diff("tuaha/acme-shop", 42)
        """
        client = self._get_client()
        url = f"/repos/{repo}/pulls/{pr_number}"

        logger.info(f"Fetching diff for {repo}#{pr_number}...")

        response = await client.get(
            url,
            headers={"Accept": "application/vnd.github.v3.diff"},
        )

        if response.status_code == 404:
            raise ValueError(f"PR #{pr_number} not found in {repo}")
        response.raise_for_status()

        diff_text = response.text
        logger.info(
            f"Fetched diff for {repo}#{pr_number}: "
            f"{len(diff_text)} chars, "
            f"{diff_text.count(chr(10))} lines"
        )
        return diff_text

    async def fetch_pr_files(self, repo: str, pr_number: int) -> list[dict]:
        """
        Fetch the list of files changed in a pull request.

        Returns a list of dicts, each with:
          - filename: "src/auth/login.py"
          - status: "modified" | "added" | "removed"
          - patch: the unified diff for this file (if available)

        This gives per-file granularity, useful for telling the agent
        which files changed.
        """
        client = self._get_client()
        url = f"/repos/{repo}/pulls/{pr_number}/files"

        logger.info(f"Fetching changed files for {repo}#{pr_number}...")

        response = await client.get(url)
        response.raise_for_status()

        files = response.json()
        file_list = [
            {
                "filename": f.get("filename", ""),
                "status": f.get("status", ""),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "patch": f.get("patch", ""),
            }
            for f in files
        ]

        logger.info(
            f"Found {len(file_list)} changed files in {repo}#{pr_number}"
        )
        return file_list

    async def post_pr_comment(
        self, repo: str, pr_number: int, body: str
    ) -> dict:
        """
        Post a comment on a pull request.

        Used to deliver agent findings directly on the PR.
        The body should be formatted Markdown.

        Args:
            repo: Repository full name
            pr_number: Pull request number
            body: Markdown-formatted comment body

        Returns:
            The created comment as a dict (from GitHub API response)
        """
        client = self._get_client()
        url = f"/repos/{repo}/issues/{pr_number}/comments"

        logger.info(f"Posting comment on {repo}#{pr_number}...")

        response = await client.post(url, json={"body": body})

        if response.status_code == 403:
            logger.error(
                "GitHub API returned 403 — check that your GITHUB_TOKEN "
                "has 'repo' scope for private repos or 'public_repo' for public."
            )
        response.raise_for_status()

        comment = response.json()
        logger.info(
            f"Posted comment on {repo}#{pr_number}: {comment.get('html_url', '')}"
        )
        return comment

    async def close(self):
        """Close the HTTP client (for clean shutdown)."""
        if self._client:
            await self._client.aclose()
            self._client = None


# ─── Singleton ───
github_client = GitHubClient()
