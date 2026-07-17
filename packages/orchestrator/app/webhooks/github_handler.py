"""
Pulse Orchestrator — GitHub Webhook Handler

This is the endpoint GitHub hits every time a PR is opened or updated.

Flow:
  1. GitHub fires a webhook → hits POST /webhook/github
  2. We read the RAW body (needed for signature verification)
  3. Verify the HMAC-SHA256 signature → reject if invalid
  4. Read X-GitHub-Event header to determine event type
  5. For pull_request events, filter to only "opened" and "synchronize"
  6. Log the payload with PR details
  7. Kick off the review pipeline as a background task
  8. Return 200 immediately (GitHub expects fast responses)
"""

import asyncio

from fastapi import APIRouter, Request, HTTPException
from app.config import settings
from app.webhooks.signature import verify_github_signature
from app.models.webhook_events import WebhookReceivedEvent
from app.models.agent_models import ReviewRequest, ReviewSource
from app.agents.review_runner import run_review
from app.ws.socket_server import emit_event
from app.utils.logger import setup_logger

logger = setup_logger("pulse.webhook")

router = APIRouter(prefix="/webhook", tags=["Webhooks"])

# PR actions we care about — ignore everything else
RELEVANT_PR_ACTIONS = {"opened", "synchronize"}


@router.post("/github")
async def handle_github_webhook(request: Request):
    """
    Receive and process GitHub webhook payloads.

    This endpoint is registered as the webhook URL in your GitHub App
    or repository webhook settings.
    """

    # ── Step 1: Read raw body (must hash raw bytes, not parsed JSON) ──
    raw_body = await request.body()

    # ── Step 2: Verify signature ──
    signature = request.headers.get("X-Hub-Signature-256", "")

    if settings.github_webhook_secret:
        if not verify_github_signature(raw_body, signature, settings.github_webhook_secret):
            logger.warning("⚠ Webhook signature verification FAILED — rejecting payload")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    else:
        logger.warning("⚠ No GITHUB_WEBHOOK_SECRET configured — skipping signature verification")

    # ── Step 3: Determine event type ──
    event_type = request.headers.get("X-GitHub-Event", "unknown")
    delivery_id = request.headers.get("X-GitHub-Delivery", "unknown")

    logger.info(f"📥 Webhook received: event={event_type}, delivery={delivery_id}")

    # ── Step 4: Parse the JSON body ──
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse webhook JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # ── Step 5: Handle based on event type ──
    if event_type == "pull_request":
        return await _handle_pull_request(payload)

    elif event_type == "ping":
        logger.info("🏓 Ping event received — webhook is connected!")
        return {"status": "pong", "message": "Webhook connected successfully"}

    else:
        logger.info(f"ℹ Ignoring event type: {event_type}")
        return {"status": "ignored", "event": event_type}


async def _handle_pull_request(payload: dict):
    """Process a pull_request webhook event."""

    action = payload.get("action", "unknown")

    # Only process relevant actions
    if action not in RELEVANT_PR_ACTIONS:
        logger.info(f"ℹ Ignoring pull_request action: {action}")
        return {"status": "ignored", "action": action}

    # Extract PR details
    try:
        pr_data = payload.get("pull_request", {})
        repo_data = payload.get("repository", {})

        pr_number = pr_data.get("number", 0)
        pr_title = pr_data.get("title", "")
        author = pr_data.get("user", {}).get("login", "unknown")
        head_sha = pr_data.get("head", {}).get("sha", "")
        base_branch = pr_data.get("base", {}).get("ref", "")
        head_branch = pr_data.get("head", {}).get("ref", "")
        repo_name = repo_data.get("full_name", "unknown")

        logger.info(
            f"🔍 PR #{pr_number} '{pr_title}' by {author} "
            f"({head_branch} → {base_branch}) — action: {action}"
        )

    except Exception as e:
        logger.error(f"Failed to parse pull_request payload: {e}")
        raise HTTPException(status_code=400, detail="Malformed pull_request payload")

    # ── Broadcast to dashboard via Socket.io ──
    event = WebhookReceivedEvent(
        event_type="pull_request",
        action=action,
        repo=repo_name,
        pr_number=pr_number,
        pr_title=pr_title,
        author=author,
    )
    await emit_event("webhook_received", event.model_dump())

    # ── Kick off the review as a background task ──
    review_request = ReviewRequest(
        diff="",  # Will be fetched from GitHub by the runner
        repo=repo_name,
        pr_number=pr_number,
        head_sha=head_sha,
        branch=head_branch,
        author=author,
        source=ReviewSource.GITHUB_PR,
    )

    # Run review in the background — don't block the webhook response
    asyncio.create_task(
        _run_review_safe(review_request, pr_number, repo_name)
    )

    logger.info(f"📡 Review triggered for PR #{pr_number} (running in background)")

    # ── Return 200 immediately ──
    return {
        "status": "review_started",
        "event": "pull_request",
        "action": action,
        "pr": pr_number,
        "repo": repo_name,
        "message": f"Review started for PR #{pr_number}",
    }


async def _run_review_safe(
    review_request: ReviewRequest,
    pr_number: int,
    repo_name: str,
):
    """
    Wrapper that catches exceptions from the background review task.
    asyncio.create_task doesn't propagate exceptions to the caller,
    so we catch them here to avoid silent failures.
    """
    try:
        result = await run_review(review_request)
        logger.info(
            f"Background review for {repo_name}#{pr_number} completed: "
            f"{result.message}"
        )
    except Exception as e:
        logger.error(
            f"Background review for {repo_name}#{pr_number} failed: {e}",
            exc_info=True,
        )
