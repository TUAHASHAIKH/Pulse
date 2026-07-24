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
from app.graph.builder import review_graph
from app.agents.formatter import format_as_github_comment
from app.integrations.github_client import github_client
from app.ws.socket_server import emit_event
from app.utils.logger import setup_logger

logger = setup_logger("pulse.review")


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
    review_id = str(uuid.uuid4())[:8]
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

    # ── Step 2: Run all agents in parallel via LangGraph ──
    logger.info(f"Review {review_id}: launching LangGraph multi-agent orchestration...")
    
    final_state = await review_graph.ainvoke({
        "diff": diff,
        "changed_files": changed_files,
        "results": []
    })
    
    results = final_state.get("results", [])

    # ── Step 3: Post PR comment (only for GitHub PRs) ──
    posted_comment = False
    if (
        request.source == ReviewSource.GITHUB_PR
        and request.repo
        and request.pr_number
    ):
        try:
            comment_body = format_as_github_comment(results)
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
    await emit_event("review_completed", {
        "review_id": review_id,
        "source": request.source.value,
        "total_findings": total_findings,
        "posted_comment": posted_comment,
        "results": [r.model_dump() for r in results],
    })

    # ── Build summary message ──
    finding_summary = f"{total_findings} total issue(s) found across {len(results)} agents"
    if posted_comment:
        message = f"{finding_summary}. Comment posted on PR."
    else:
        message = finding_summary

    logger.info(f"Review {review_id} completed: {message}")

    return ReviewAPIResponse(
        status="completed",
        review_id=review_id,
        results=results,
        posted_comment=posted_comment,
        message=message,
    )
