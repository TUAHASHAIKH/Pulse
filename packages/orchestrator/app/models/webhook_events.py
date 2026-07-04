"""
Pulse Orchestrator — Webhook Event Models

Pydantic models for the GitHub webhook payloads we care about.
These give us:
  - Type safety (catch bad payloads early, not deep in agent code)
  - Auto-generated API docs in FastAPI's /docs page
  - Clean serialization for Socket.io events
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ─── Incoming GitHub Webhook Payloads ───


class GitHubUser(BaseModel):
    """GitHub user who authored the PR."""
    login: str
    avatar_url: str = ""


class GitHubRepo(BaseModel):
    """Repository the PR belongs to."""
    full_name: str          # e.g. "tuaha/acme-shop"
    clone_url: str = ""     # for cloning into the sandbox later
    default_branch: str = "main"


class PullRequestData(BaseModel):
    """Core pull request fields extracted from the webhook payload."""
    number: int
    title: str
    state: str                      # "open", "closed"
    user: GitHubUser
    head_sha: str = Field("", alias="head_sha")
    base_branch: str = ""
    head_branch: str = ""
    diff_url: str = ""
    html_url: str = ""
    body: Optional[str] = None      # PR description

    model_config = {"populate_by_name": True}


class PullRequestEvent(BaseModel):
    """
    Parsed from the GitHub pull_request webhook payload.
    Only the fields we actually need — GitHub sends a LOT more.
    """
    action: str                     # "opened", "synchronize", "closed"
    pull_request: PullRequestData
    repository: GitHubRepo


# ─── Internal Event Models (for Socket.io + inter-module) ───


class WebhookReceivedEvent(BaseModel):
    """Emitted over Socket.io when a webhook is received and validated."""
    event_type: str                 # "pull_request", "push", etc.
    action: str                     # "opened", "synchronize", etc.
    repo: str                       # "tuaha/acme-shop"
    pr_number: Optional[int] = None
    pr_title: Optional[str] = None
    author: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class HealthResponse(BaseModel):
    """Response from GET /health."""
    status: str = "ok"
    version: str = "0.1.0"
    uptime_seconds: Optional[float] = None
