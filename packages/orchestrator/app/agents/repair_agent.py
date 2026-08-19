"""
Pulse Orchestrator — Repair Agent
"""

from __future__ import annotations

import time
from typing import Optional

from app.context.context_builder import read_full_file
from app.context.diff_parser import ParsedDiff, format_hunks_for_file, parse_diff
from app.integrations.llm_client import llm_client
from app.models.agent_models import Finding, TokenUsage
from app.utils.logger import setup_logger
from app.utils.prompts import get_prompt_path

logger = setup_logger("pulse.agent.repair")

AGENT_NAME = "repair"


def _load_system_prompt() -> str:
    prompt_path = get_prompt_path("repair")
    if not prompt_path.exists():
        raise FileNotFoundError(f"Repair agent prompt not found at {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def _build_user_message(
    finding: Finding,
    diff: str,
    previous_errors: Optional[list[str]] = None,
    project_root: Optional[str] = None,
    parsed_diff: Optional[ParsedDiff] = None,
) -> str:
    parts: list[str] = []

    parts.append("## Finding to Fix")
    parts.append(f"**File:** `{finding.file}` (line {finding.line})")
    parts.append(f"**Severity:** {finding.severity.value}")
    parts.append(f"**Category:** {finding.category}")
    parts.append(f"**Title:** {finding.title}")
    parts.append(f"**Explanation:** {finding.explanation}")
    if finding.evidence:
        parts.append(f"**Evidence from diff:** `{finding.evidence}`")
    if finding.suggested_fix:
        parts.append(f"**Agent's Suggestion (UNVERIFIED HINT):** {finding.suggested_fix}")
    parts.append("")

    full_file = read_full_file(project_root, finding.file) if project_root else None
    if full_file:
        parts.append("## Authoritative File Content (generate patch against THIS)")
        parts.append(f"### `{finding.file}`")
        parts.append("```")
        parts.append(full_file)
        parts.append("```")
        parts.append("")

    parsed = parsed_diff or parse_diff(diff)
    hunk_text = format_hunks_for_file(parsed, finding.file)
    if hunk_text:
        parts.append("## Diff Hunk Containing Issue")
        parts.append("```diff")
        parts.append(hunk_text)
        parts.append("```")
        parts.append("")
    else:
        parts.append("## Original Diff (containing the issue)")
        parts.append("```diff")
        parts.append(diff[:12000])
        parts.append("```")
        parts.append("")

    if previous_errors:
        parts.append("## Previous Repair Attempts (FAILED)")
        parts.append(
            "Learn from these errors and try a different approach:"
        )
        for i, error in enumerate(previous_errors, 1):
            parts.append(f"\n### Attempt {i}")
            parts.append("```")
            parts.append(error[:2000])
            parts.append("```")
        parts.append("")

    return "\n".join(parts)


def _parse_repair_response(parsed_json: Optional[dict | list]) -> tuple[str, str, float, list[str]]:
    if parsed_json is None:
        return "", "Failed to parse LLM response as JSON", 0.0, []

    if not isinstance(parsed_json, dict):
        return "", "Unexpected LLM response format", 0.0, []

    patch = parsed_json.get("patch", "")
    explanation = parsed_json.get("explanation", "")
    confidence = parsed_json.get("confidence", 0.5)
    files_modified = parsed_json.get("files_modified", [])

    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.5

    return patch, explanation, confidence, files_modified


async def generate_fix(
    finding: Finding,
    diff: str,
    previous_errors: Optional[list[str]] = None,
    model: Optional[str] = None,
    project_root: Optional[str] = None,
) -> dict:
    previous_errors = previous_errors or []
    start_time = time.time()
    attempt_num = len(previous_errors) + 1

    logger.info(
        f"Repair Agent generating fix for '{finding.title}' "
        f"(attempt {attempt_num}, file: {finding.file})"
    )

    try:
        system_prompt = _load_system_prompt()
        user_message = _build_user_message(
            finding, diff, previous_errors, project_root
        )

        response = await llm_client.call(
            system_prompt=system_prompt,
            user_message=user_message,
            model=model,
        )

        patch, explanation, confidence, files_modified = _parse_repair_response(
            response.parsed_json
        )
        duration = time.time() - start_time

        logger.info(
            f"Repair Agent generated patch — confidence: {confidence:.2f}, "
            f"{len(patch)} chars, {duration:.1f}s"
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
