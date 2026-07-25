"""
Pulse Orchestrator — Repair Agent

The Repair Agent receives critical findings from reviewer agents and
generates fix patches using the LLM. It does NOT apply fixes itself —
that's the job of the repair_runner (Docker sandbox) and fix_applicator.

Flow:
  1. Receive a Finding + original diff context
  2. Load the repair system prompt from docs/agent-prompts/
  3. Build a message with the finding details + any previous failed attempts
  4. Ask the LLM to produce a unified diff patch
  5. Parse and validate the patch
  6. Return a structured result

Design decision: The Repair Agent is stateless and focused.
It generates ONE patch per call. The retry loop (with test feedback)
lives in repair_runner.py.
"""

import time
from pathlib import Path
from typing import Optional

from app.integrations.llm_client import llm_client
from app.models.agent_models import (
    Finding,
    RepairResult,
    RepairStatus,
    TokenUsage,
)
from app.ws.socket_server import emit_event
from app.utils.logger import setup_logger

logger = setup_logger("pulse.agent.repair")

# Path to the versioned system prompt
PROMPT_PATH = Path(__file__).resolve().parents[4] / "docs" / "agent-prompts" / "repair_agent.md"

AGENT_NAME = "repair"


def _load_system_prompt() -> str:
    """Load the repair agent's system prompt from the versioned file."""
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"Repair agent prompt not found at {PROMPT_PATH}. "
            f"Expected it in docs/agent-prompts/repair_agent.md"
        )

    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _build_user_message(
    finding: Finding,
    diff: str,
    previous_errors: Optional[list[str]] = None,
) -> str:
    """
    Build the user message sent to the LLM.

    Includes the finding details, original diff, and any error
    feedback from previous failed repair attempts.
    """
    parts = []

    # Finding details
    parts.append("## Finding to Fix")
    parts.append(f"**File:** `{finding.file}` (line {finding.line})")
    parts.append(f"**Severity:** {finding.severity.value}")
    parts.append(f"**Category:** {finding.category}")
    parts.append(f"**Title:** {finding.title}")
    parts.append(f"**Explanation:** {finding.explanation}")
    if finding.suggested_fix:
        parts.append(f"**Agent's Suggestion:** {finding.suggested_fix}")
    parts.append("")

    # Original diff context
    parts.append("## Original Diff (containing the issue)")
    parts.append("```diff")
    parts.append(diff)
    parts.append("```")
    parts.append("")

    # Previous failed attempts (for retry loop feedback)
    if previous_errors:
        parts.append("## Previous Repair Attempts (FAILED)")
        parts.append(
            "The following previous fix attempts failed testing. "
            "Learn from these errors and try a different approach:"
        )
        for i, error in enumerate(previous_errors, 1):
            parts.append(f"\n### Attempt {i} — Test Failure")
            parts.append("```")
            parts.append(error[:2000])  # Cap error output length
            parts.append("```")
        parts.append("")

    return "\n".join(parts)


def _parse_repair_response(parsed_json: Optional[dict | list]) -> tuple[str, str, float, list[str]]:
    """
    Parse the LLM's JSON response into repair components.

    Returns:
        (patch, explanation, confidence, files_modified)
    """
    if parsed_json is None:
        return "", "Failed to parse LLM response as JSON", 0.0, []

    if not isinstance(parsed_json, dict):
        return "", "Unexpected LLM response format", 0.0, []

    patch = parsed_json.get("patch", "")
    explanation = parsed_json.get("explanation", "")
    confidence = parsed_json.get("confidence", 0.5)
    files_modified = parsed_json.get("files_modified", [])

    # Validate confidence range
    try:
        confidence = float(confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.5

    return patch, explanation, confidence, files_modified


async def generate_fix(
    finding: Finding,
    diff: str,
    previous_errors: Optional[list[str]] = None,
    model: Optional[str] = None,
) -> dict:
    """
    Generate a fix patch for a single critical finding.

    Args:
        finding: The Finding object to fix
        diff: The original diff containing the issue
        previous_errors: Error output from previous failed attempts
        model: Optional LLM model override

    Returns:
        Dict with keys: patch, explanation, confidence, files_modified
    """
    previous_errors = previous_errors or []
    start_time = time.time()

    attempt_num = len(previous_errors) + 1
    logger.info(
        f"Repair Agent generating fix for '{finding.title}' "
        f"(attempt {attempt_num}, file: {finding.file})"
    )

    try:
        # Load prompt
        system_prompt = _load_system_prompt()

        # Build message
        user_message = _build_user_message(finding, diff, previous_errors)

        # Call LLM
        response = await llm_client.call(
            system_prompt=system_prompt,
            user_message=user_message,
            model=model,
        )

        # Parse response
        patch, explanation, confidence, files_modified = _parse_repair_response(
            response.parsed_json
        )

        duration = time.time() - start_time

        logger.info(
            f"Repair Agent generated patch — "
            f"confidence: {confidence:.2f}, "
            f"{len(patch)} chars, "
            f"{duration:.1f}s"
        )

        return {
            "patch": patch,
            "explanation": explanation,
            "confidence": confidence,
            "files_modified": files_modified,
            "token_usage": response.token_usage,
            "duration": round(duration, 2),
        }

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Repair Agent failed: {e}")
        return {
            "patch": "",
            "explanation": f"Repair Agent error: {str(e)}",
            "confidence": 0.0,
            "files_modified": [],
            "token_usage": TokenUsage(),
            "duration": round(duration, 2),
        }
