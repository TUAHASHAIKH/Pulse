"""
Pulse Orchestrator — Review Runner

Orchestrates a single review run. This is the glue between
triggers (webhook, CLI, API) and agents.

Flow:
  1. Accept a ReviewRequest (trigger-agnostic)
  2. If source is GitHub PR and no diff provided → fetch from GitHub
  3. Run the Security Agent on the diff
  4. If source is GitHub PR → post findings as a PR comment
  5. Emit Socket.io events at each step
  6. Return the results (for API response / CLI output)

In Phase 3, this becomes the LangGraph Architect Agent that
fans out to multiple agents in parallel. For now, it's a simple
sequential function that calls the Security Agent directly.

Design decision: The runner posts a PR comment ONLY when the
trigger was a GitHub PR. For CLI/manual reviews, results are
returned to the caller without posting anywhere.
"""

import uuid
from typing import Optional

from app.models.agent_models import (
    ReviewRequest,
    ReviewSource,
    AgentResult,
    ReviewAPIResponse,
)
from app.config import get_project_root
from app.graph.builder import review_graph
from app.agents.formatter import format_as_github_comment
from app.agents import fix_applicator
from app.integrations.github_client import github_client
from app.ws.socket_server import emit_event
from app.utils.logger import setup_logger

logger = setup_logger("pulse.review")

# In-memory store of completed reviews — keyed by review_id.
# Used by the fix application endpoints to look up patches.
# In a production system, this would be a database.
_review_store: dict[str, dict] = {}


def get_review(review_id: str) -> dict | None:
    """Look up a completed review by ID."""
    return _review_store.get(review_id)


async def run_review(request: ReviewRequest) -> ReviewAPIResponse:
    """
    Run a full code review on the given request.

    This is the single entry point for ALL review triggers:
      - GitHub webhook calls this after extracting the PR details
      - POST /api/review calls this after building a ReviewRequest
      - CLI will call this after reading the local diff

    Args:
        request: Trigger-agnostic review input

    Returns:
        ReviewAPIResponse with all agent results
    """
    review_id = request.review_id or str(uuid.uuid4())[:8]
    logger.info(f"Review {review_id} started — source: {request.source.value}")

    # ── Emit: review started ──
    await emit_event("review_started", {
        "review_id": review_id,
        "source": request.source.value,
        "repo": request.repo,
        "pr_number": request.pr_number,
    })

    # ── Step 1: Get the diff (if not already provided) ──
    diff = request.diff
    changed_files = request.changed_files

    if not diff and request.repo and request.pr_number:
        # Fetch diff from GitHub
        try:
            diff = await github_client.fetch_pr_diff(
                request.repo, request.pr_number
            )

            # Also fetch the list of changed files
            files_data = await github_client.fetch_pr_files(
                request.repo, request.pr_number
            )
            changed_files = [f["filename"] for f in files_data]

        except Exception as e:
            logger.error(f"Failed to fetch diff from GitHub: {e}")
            return ReviewAPIResponse(
                status="error",
                review_id=review_id,
                message=f"Failed to fetch diff: {str(e)}",
            )

    if not diff:
        return ReviewAPIResponse(
            status="error",
            review_id=review_id,
            message="No diff provided and no GitHub PR to fetch from. "
                    "Provide either a 'diff' string or 'repo' + 'pr_number'.",
        )

    # ── Step 2: Run all agents (+ repair) via LangGraph ──
    logger.info(f"Review {review_id}: launching LangGraph multi-agent orchestration...")
    
    project_root = request.project_root or get_project_root()

    final_state = await review_graph.ainvoke({
        "diff": diff,
        "changed_files": changed_files,
        "project_root": project_root or "",
        "results": [],
        "repair_results": [],
    })
    
    results = final_state.get("results", [])
    repair_results = final_state.get("repair_results", [])

    # ── Step 2b: Auto-deliver fixes per fix_delivery setting ──
    fix_deliveries = await fix_applicator.auto_deliver_repairs(
        repair_results=repair_results,
        review_id=review_id,
        project_root=project_root or "",
        repo=request.repo,
        pr_number=request.pr_number,
    )
    for delivery in fix_deliveries:
        await emit_event("fix_delivered", {
            "review_id": review_id,
            "method": delivery.method,
            "success": delivery.success,
            "message": delivery.message,
            "files_changed": delivery.files_changed,
            "branch_name": delivery.branch_name,
        })

    # ── Step 3: Post PR comment (only for GitHub PRs) ──
    posted_comment = False
    if (
        request.source == ReviewSource.GITHUB_PR
        and request.repo
        and request.pr_number
    ):
        try:
            comment_body = format_as_github_comment(results, repair_results)
            await github_client.post_pr_comment(
                request.repo, request.pr_number, comment_body
            )
            posted_comment = True
            logger.info(
                f"Review {review_id}: posted comment on "
                f"{request.repo}#{request.pr_number}"
            )
        except Exception as e:
            logger.error(f"Failed to post PR comment: {e}")

    # ── Step 4: Emit completion event ──
    total_findings = sum(len(r.findings) for r in results)
    total_repairs = sum(1 for r in repair_results if r.status.value == "succeeded")
    await emit_event("review_completed", {
        "review_id": review_id,
        "source": request.source.value,
        "total_findings": total_findings,
        "total_repairs": total_repairs,
        "posted_comment": posted_comment,
        "results": [r.model_dump() for r in results],
        "repair_results": [r.model_dump() for r in repair_results],
    })

    # ── Build summary message ──
    finding_summary = f"{total_findings} total issue(s) found across {len(results)} agents"
    if total_repairs:
        finding_summary += f", {total_repairs} fix(es) available"
    if posted_comment:
        message = f"{finding_summary}. Comment posted on PR."
    else:
        message = finding_summary

    logger.info(f"Review {review_id} completed: {message}")

    # Store results globally for fix application later
    _review_store[review_id] = {
        "results": results,
        "repair_results": repair_results,
        "request": request,
    }

    return ReviewAPIResponse(
        status="completed",
        review_id=review_id,
        results=results,
        repair_results=repair_results,
        posted_comment=posted_comment,
        message=message,
    )
