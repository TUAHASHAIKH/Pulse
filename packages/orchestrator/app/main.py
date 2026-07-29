"""
Pulse Orchestrator — Main Entrypoint

This is where everything comes together:
  - FastAPI app is created with CORS, health endpoint, and webhook routes
  - Socket.io ASGI app is mounted alongside FastAPI
  - Both share the same process and port

Run with:
  uvicorn app.main:app --reload --port 8000

Architecture:
  ┌──────────────────────────────────────────┐
  │              ASGI Application             │
  │                                          │
  │   /health              → FastAPI          │
  │   /webhook/github      → FastAPI          │
  │   /api/review          → FastAPI (Phase 2)│
  │   /docs                → FastAPI (Swagger)│
  │   /socket.io/*         → Socket.io        │
  └──────────────────────────────────────────┘
"""

import time
import subprocess
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, get_project_root
from app.webhooks.github_handler import router as webhook_router
from app.ws.socket_server import socket_app
from app.models.webhook_events import HealthResponse
from app.models.agent_models import (
    ReviewRequest, ReviewSource, ReviewAPIRequest, ReviewAPIResponse,
    FixApplicationRequest, FixApplicationResponse, FixDeliveryMethod,
)
from app.agents.review_runner import run_review, get_review
from app.agents import fix_applicator
from app import settings_store
from app.utils.logger import setup_logger

logger = setup_logger("pulse.main")

# Track server start time for uptime calculation
_start_time: float = 0.0


# ─── Lifespan (startup / shutdown) ───

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on server startup and shutdown.
    Startup: log config, set start time.
    Shutdown: clean up resources.
    """
    global _start_time
    _start_time = time.time()

    logger.info("=" * 60)
    logger.info("  🫀 PULSE ORCHESTRATOR starting up")
    logger.info("=" * 60)
    logger.info(f"  Config loaded:    {settings.config_source}")
    logger.info(f"  Port:             {settings.orchestrator_port}")
    logger.info(f"  Log level:        {settings.log_level}")
    logger.info(f"  Dashboard CORS:   {settings.dashboard_origin}")
    logger.info(f"  Webhook secret:   {'configured ✓' if settings.github_webhook_secret else 'NOT SET ⚠'}")
    logger.info(f"  GitHub token:     {'configured ✓' if settings.github_token else 'NOT SET (needed for PR comments)'}")
    logger.info(f"  LLM provider:     {settings.llm_provider}")
    logger.info(f"  LLM API key:      {'configured ✓' if settings.llm_api_key else 'NOT SET ⚠'}")
    logger.info("=" * 60)

    yield  # Server is running

    logger.info("🫀 Pulse Orchestrator shutting down...")


# ─── Create FastAPI App ───

app = FastAPI(
    title="Pulse Orchestrator",
    description=(
        "Autonomous multi-agent DevOps system. "
        "Receives GitHub webhooks, coordinates AI agents for code review, "
        "and manages automated repair and self-healing."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ─── CORS Middleware ───
# Allow the Next.js dashboard to make requests to the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.dashboard_origin,
        "http://localhost:3000",
        "http://localhost:4000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Register Routes ───
app.include_router(webhook_router)


# ─── Review API (trigger-agnostic) ───

def _filter_noise_from_diff(diff: str) -> str:
    """
    Remove diff hunks for non-code / noise files (such as .gitignore, lockfiles, .pulse/ config)
    so agents only review meaningful source code changes.
    """
    if not diff or not diff.strip():
        return ""

    noise_patterns = (
        ".gitignore",
        ".antigravityignore",
        ".gitattributes",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Cargo.lock",
        ".pulse/",
    )

    sections = []
    current_section = []
    ignore_current = False

    for line in diff.split("\n"):
        if line.startswith("diff --git "):
            if current_section and not ignore_current:
                sections.append("\n".join(current_section))
            current_section = [line]
            ignore_current = any(p in line for p in noise_patterns)
        else:
            current_section.append(line)

    if current_section and not ignore_current:
        sections.append("\n".join(current_section))

    return "\n\n".join(sections).strip()


def _get_local_git_diff() -> str:
    """
    Get the git diff of the user's project directory.
    First tries staged changes (`git diff --cached`),
    then falls back to all unstaged changes (`git diff HEAD`).
    Filters out config/lockfile noise (.gitignore, package-lock.json, etc.).
    """
    project_root = get_project_root() or str(Path.cwd())
    try:
        res = subprocess.run(
            ["git", "diff", "--cached"],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        diff = _filter_noise_from_diff(res.stdout)
        if not diff or not diff.strip():
            res_head = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            diff = _filter_noise_from_diff(res_head.stdout)
        return diff or ""
    except Exception as e:
        logger.warning(f"Could not read git diff from {project_root}: {e}")
        return ""


@app.post("/api/review", response_model=ReviewAPIResponse, tags=["Review"])
async def api_review(request: ReviewAPIRequest):
    """
    Trigger a code review manually.

    Accepts EITHER:
      - A raw diff string (for local/manual reviews)
      - A repo + pr_number (to fetch the diff from GitHub)
      - Empty body (automatically reviews local git changes in project directory)

    This is the same review pipeline that GitHub webhooks use,
    but triggered on-demand. Useful for:
      - Testing without setting up webhooks
      - CLI integration (pulse review)
      - Reviewing local changes before pushing
    """
    # Build a trigger-agnostic ReviewRequest
    if request.diff:
        review_request = ReviewRequest(
            diff=request.diff,
            source=ReviewSource.MANUAL,
        )
    elif request.repo and request.pr_number:
        # We'll fetch the diff inside the runner
        review_request = ReviewRequest(
            diff="",  # Will be fetched from GitHub
            repo=request.repo,
            pr_number=request.pr_number,
            source=ReviewSource.GITHUB_PR,
        )
    else:
        # No diff or PR provided -> Automatically grab the local git diff!
        local_diff = _get_local_git_diff()
        if not local_diff or not local_diff.strip():
            return ReviewAPIResponse(
                status="error",
                message="No changes detected in local git repository (git diff is empty). Make some edits or stage changes with `git add` first.",
            )
        review_request = ReviewRequest(
            diff=local_diff,
            source=ReviewSource.MANUAL,
        )

    return await run_review(review_request)


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Health check endpoint.
    Returns server status and uptime. Useful for monitoring
    and confirming the orchestrator is alive.
    """
    return HealthResponse(
        status="ok",
        version="0.1.0",
        uptime_seconds=round(time.time() - _start_time, 2),
    )


# ─── Fix Application API (Phase 4) ───


@app.post("/api/fix/apply-local", response_model=FixApplicationResponse, tags=["Fix"])
async def apply_fix_locally(request: FixApplicationRequest):
    """
    Apply a verified fix to the user's local filesystem.
    Uses `git apply` — changes files but does NOT commit.
    """
    review = get_review(request.review_id)
    if not review:
        return FixApplicationResponse(
            success=False, method="local",
            message=f"Review '{request.review_id}' not found.",
        )

    repair_results = review.get("repair_results", [])
    matching = [r for r in repair_results if r.finding_index == request.finding_index]
    if not matching:
        return FixApplicationResponse(
            success=False, method="local",
            message=f"No repair found for finding index {request.finding_index}.",
        )

    repair = matching[0]
    from app.config import get_project_root
    project_root = get_project_root() or "."

    return await fix_applicator.apply_locally(repair.patch, project_root)


@app.post("/api/fix/pr-comment", response_model=FixApplicationResponse, tags=["Fix"])
async def post_fix_as_comment(request: FixApplicationRequest):
    """
    Post a verified fix as a comment on a GitHub PR.
    """
    review = get_review(request.review_id)
    if not review:
        return FixApplicationResponse(
            success=False, method="pr_comment",
            message=f"Review '{request.review_id}' not found.",
        )

    repair_results = review.get("repair_results", [])
    matching = [r for r in repair_results if r.finding_index == request.finding_index]
    if not matching:
        return FixApplicationResponse(
            success=False, method="pr_comment",
            message=f"No repair found for finding index {request.finding_index}.",
        )

    repair = matching[0]
    repo = request.repo or review.get("request", {}).repo
    pr_number = request.pr_number or review.get("request", {}).pr_number

    if not repo or not pr_number:
        return FixApplicationResponse(
            success=False, method="pr_comment",
            message="Missing repo or pr_number for PR comment.",
        )

    return await fix_applicator.post_as_pr_comment(
        patch=repair.patch,
        explanation=repair.explanation,
        finding_title=repair.finding_title,
        repo=repo,
        pr_number=pr_number,
    )


@app.post("/api/fix/commit-branch", response_model=FixApplicationResponse, tags=["Fix"])
async def commit_fix_to_branch(request: FixApplicationRequest):
    """
    Commit a verified fix to a new branch on GitHub.
    Creates pulse/fix-{review_id} branch.
    """
    review = get_review(request.review_id)
    if not review:
        return FixApplicationResponse(
            success=False, method="branch",
            message=f"Review '{request.review_id}' not found.",
        )

    repair_results = review.get("repair_results", [])
    matching = [r for r in repair_results if r.finding_index == request.finding_index]
    if not matching:
        return FixApplicationResponse(
            success=False, method="branch",
            message=f"No repair found for finding index {request.finding_index}.",
        )

    repair = matching[0]
    repo = request.repo or review.get("request", {}).repo
    pr_number = request.pr_number or review.get("request", {}).pr_number

    if not repo or not pr_number:
        return FixApplicationResponse(
            success=False, method="branch",
            message="Missing repo or pr_number for branch commit.",
        )

    return await fix_applicator.commit_to_branch(
        patch=repair.patch,
        explanation=repair.explanation,
        finding_title=repair.finding_title,
        review_id=request.review_id,
        repo=repo,
        pr_number=pr_number,
    )


# ─── Settings API ───


@app.get("/api/settings", tags=["Settings"])
async def get_settings():
    """Get current user settings."""
    return settings_store.load_settings()


@app.post("/api/settings", tags=["Settings"])
async def update_settings(settings_data: dict):
    """Update user settings."""
    current = settings_store.load_settings()
    current.update(settings_data)
    success = settings_store.save_settings(current)
    return {"success": success, "settings": current}


# ─── Mount Socket.io ───
# Socket.io is mounted as a sub-application at /socket.io/
# This means FastAPI handles /health, /webhook/*, /docs
# and Socket.io handles /socket.io/* — all on the same port
app.mount("/socket.io", socket_app)


# ─── Direct Run (alternative to uvicorn CLI) ───

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.orchestrator_port,
        reload=True,
    )
