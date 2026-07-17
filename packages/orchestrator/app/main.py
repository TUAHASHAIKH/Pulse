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
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.webhooks.github_handler import router as webhook_router
from app.ws.socket_server import socket_app
from app.models.webhook_events import HealthResponse
from app.models.agent_models import ReviewRequest, ReviewSource, ReviewAPIRequest, ReviewAPIResponse
from app.agents.review_runner import run_review
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

@app.post("/api/review", response_model=ReviewAPIResponse, tags=["Review"])
async def api_review(request: ReviewAPIRequest):
    """
    Trigger a code review manually.

    Accepts EITHER:
      - A raw diff string (for local/manual reviews)
      - A repo + pr_number (to fetch the diff from GitHub)

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
        return ReviewAPIResponse(
            status="error",
            message="Provide either a 'diff' string or 'repo' + 'pr_number'.",
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
