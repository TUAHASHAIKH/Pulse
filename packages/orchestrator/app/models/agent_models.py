"""
Pulse Orchestrator — Agent Models

Shared data schemas for all agents. These define:
  - ReviewRequest: trigger-agnostic input (works for GitHub PRs, CLI, manual)
  - Finding: a single issue found by an agent
  - AgentResult: what an agent returns after analysis
  - TokenUsage: LLM token tracking for cost awareness

Design decisions:
  - ReviewRequest is generic — it takes a diff string, not a GitHub payload.
    Different triggers (webhook, CLI, API) produce this input differently.
  - Finding includes a suggested_fix but applying it is a separate user action.
    The agent recommends; the user decides.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


# ─── Enums ───


class Severity(str, Enum):
    """How serious a finding is."""
    CRITICAL = "critical"   # Exploitable vulnerability (SQL injection, RCE)
    WARNING = "warning"     # Potential risk, worth investigating
    INFO = "info"           # Best practice suggestion, not a vulnerability


class ReviewSource(str, Enum):
    """Where the review request came from."""
    GITHUB_PR = "github_pr"     # Triggered by a GitHub webhook
    CLI = "cli"                 # Triggered by `pulse review` command
    MANUAL = "manual"           # Triggered by POST /api/review
    LOCAL = "local"             # Local diff (uncommitted changes)
    FULL_AUDIT = "full_audit"   # Full repository audit (pulse review --all)


# ─── Review Input (trigger-agnostic) ───


class ReviewRequest(BaseModel):
    """
    Generic input for a code review — works for any trigger source.

    Different triggers produce this differently:
      - GitHub webhook: fetches diff via GitHub API, fills in repo/pr_number
      - pulse review CLI: reads local git diff, fills in diff directly
      - POST /api/review: user provides either a raw diff or a repo+PR to fetch

    The core review pipeline only cares about the `diff` field.
    Everything else is metadata for routing results (e.g., where to post comments).
    """
    # ── Required: the code to review ──
    diff: str = Field(
        ...,
        description="Unified diff text to analyze"
    )
    changed_files: list[str] = Field(
        default_factory=list,
        description="List of file paths that were changed"
    )
    review_id: Optional[str] = Field(
        default=None,
        description="Optional shared ID for batched reviews"
    )

    # ── Source metadata (where did this come from?) ──
    source: ReviewSource = Field(
        default=ReviewSource.MANUAL,
        description="What triggered this review"
    )

    # ── GitHub-specific (only set when source is github_pr) ──
    repo: Optional[str] = Field(
        default=None,
        description="GitHub repo full name, e.g. 'tuaha/acme-shop'"
    )
    pr_number: Optional[int] = Field(
        default=None,
        description="GitHub PR number"
    )
    head_sha: Optional[str] = Field(
        default=None,
        description="Git SHA of the PR head commit"
    )

    # ── General metadata ──
    branch: Optional[str] = Field(
        default=None,
        description="Branch name being reviewed"
    )
    author: Optional[str] = Field(
        default=None,
        description="Who authored the code"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )


# ─── Agent Output ───


class TokenUsage(BaseModel):
    """Track LLM token usage for cost awareness."""
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class Finding(BaseModel):
    """
    A single issue found by an agent.

    Includes a suggested fix, but applying it is a separate user action.
    The agent recommends; the user decides.
    """
    file: str = Field(
        ...,
        description="File path where the issue was found, e.g. 'src/auth/login.py'"
    )
    line: int = Field(
        ...,
        description="Line number in the file (from the diff)"
    )
    severity: Severity = Field(
        ...,
        description="How serious: critical, warning, or info"
    )
    category: str = Field(
        ...,
        description="Issue category, e.g. 'sql-injection', 'xss', 'hardcoded-secret'"
    )
    title: str = Field(
        ...,
        description="One-line summary of the issue"
    )
    explanation: str = Field(
        ...,
        description="Plain-language explanation of why this is a problem"
    )
    suggested_fix: str = Field(
        default="",
        description="Code snippet showing how to fix the issue"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="How confident the agent is (0.0 to 1.0)"
    )


class AgentResult(BaseModel):
    """
    What an agent returns after analyzing code.

    This is the universal output format for ALL agents
    (security, performance, code quality) — same schema,
    different findings.
    """
    agent_name: str = Field(
        ...,
        description="Which agent produced this: 'security', 'performance', 'code_quality'"
    )
    findings: list[Finding] = Field(
        default_factory=list,
        description="List of issues found"
    )
    summary: str = Field(
        default="",
        description="Human-readable summary, e.g. 'Found 2 critical, 1 warning issues'"
    )
    token_usage: TokenUsage = Field(
        default_factory=TokenUsage
    )
    duration_seconds: float = Field(
        default=0.0,
        description="How long the agent took to run"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if the agent failed"
    )

    @property
    def has_critical(self) -> bool:
        return any(f.severity == Severity.CRITICAL for f in self.findings)

    @property
    def finding_counts(self) -> dict:
        counts = {"critical": 0, "warning": 0, "info": 0}
        for f in self.findings:
            counts[f.severity.value] = counts.get(f.severity.value, 0) + 1
        return counts


# ─── Repair Agent Models (Phase 4) ───


class RepairStatus(str, Enum):
    """Current status of a repair attempt."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class FixDeliveryMethod(str, Enum):
    """How a verified fix should be delivered to the user."""
    ASK = "ask"              # Show buttons in dashboard (default)
    LOCAL = "local"          # Apply to local filesystem via git apply
    PR_COMMENT = "pr_comment"  # Post as a PR comment on GitHub
    BRANCH = "branch"        # Commit to a new pulse/fix-{id} branch


class RepairResult(BaseModel):
    """
    Result of a single repair attempt for a critical finding.

    Includes the patch, test output, and metadata about the repair process.
    The patch is in unified diff format and can be applied via git apply.
    """
    finding_index: int = Field(
        ...,
        description="Index of the finding in the agent's results that this repair targets"
    )
    finding_title: str = Field(
        default="",
        description="Title of the finding being repaired (for display)"
    )
    finding_file: str = Field(
        default="",
        description="File path of the finding being repaired"
    )
    patch: str = Field(
        default="",
        description="Unified diff patch that fixes the issue"
    )
    explanation: str = Field(
        default="",
        description="Human-readable explanation of what the fix does"
    )
    test_output: str = Field(
        default="",
        description="stdout/stderr from running tests after applying the patch"
    )
    tests_passed: bool = Field(
        default=False,
        description="Whether the test suite passed after applying the patch"
    )
    attempts_taken: int = Field(
        default=0,
        description="Number of attempts it took (1-3)"
    )
    status: RepairStatus = Field(
        default=RepairStatus.PENDING,
        description="Current status of this repair"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="LLM's confidence in the fix"
    )
    duration_seconds: float = Field(
        default=0.0,
        description="Total time spent on all attempts"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if the repair failed"
    )


# ─── API Request/Response Models ───


class ReviewAPIRequest(BaseModel):
    """
    Request body for POST /api/review.

    Users can provide EITHER:
      - A raw diff string (for local/manual reviews)
      - A repo + pr_number (to fetch the diff from GitHub)
    """
    # Option 1: Raw diff
    diff: Optional[str] = Field(
        default=None,
        description="Raw unified diff text to review"
    )

    # Option 2: GitHub PR reference
    repo: Optional[str] = Field(
        default=None,
        description="GitHub repo, e.g. 'tuaha/acme-shop'"
    )
    pr_number: Optional[int] = Field(
        default=None,
        description="GitHub PR number to fetch and review"
    )


class ReviewAPIResponse(BaseModel):
    """Response from POST /api/review or POST /api/review/full."""
    status: str = "completed"
    review_id: str = ""
    results: list[AgentResult] = Field(default_factory=list)
    repair_results: list[RepairResult] = Field(default_factory=list)
    posted_comment: bool = False
    message: str = ""
    scan_stats: Optional[dict] = Field(
        default=None,
        description="File scan statistics for full audit mode (files_total, files_scanned, files_skipped, files_oversized)"
    )


class FullAuditAPIRequest(BaseModel):
    """Request body for POST /api/review/full."""
    force: bool = Field(
        default=False,
        description="If True, re-scan all files even if unchanged since last audit"
    )


class FixApplicationRequest(BaseModel):
    """Request to apply a verified fix via one of the delivery methods."""
    review_id: str = Field(
        ...,
        description="The review that produced this fix"
    )
    finding_index: int = Field(
        ...,
        description="Index of the finding/repair to apply"
    )
    method: FixDeliveryMethod = Field(
        default=FixDeliveryMethod.LOCAL,
        description="How to deliver the fix"
    )
    # GitHub-specific (needed for pr_comment and branch methods)
    repo: Optional[str] = Field(
        default=None,
        description="GitHub repo full name (for PR comment / branch)"
    )
    pr_number: Optional[int] = Field(
        default=None,
        description="GitHub PR number (for PR comment / branch)"
    )


class FixApplicationResponse(BaseModel):
    """Response after applying a fix."""
    success: bool = False
    method: str = ""
    message: str = ""
    # Method-specific details
    files_changed: list[str] = Field(default_factory=list)
    branch_name: Optional[str] = None
    comment_url: Optional[str] = None
