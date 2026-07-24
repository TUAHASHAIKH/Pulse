"""
Pulse Orchestrator — Code Quality Agent
"""

import time
from pathlib import Path
from typing import Optional

from app.integrations.llm_client import llm_client
from app.models.agent_models import (
    AgentResult,
    Finding,
    Severity,
    TokenUsage,
)
from app.ws.socket_server import emit_event
from app.utils.logger import setup_logger

logger = setup_logger("pulse.agent.code_quality")

# Path to the versioned system prompt
PROMPT_PATH = Path(__file__).resolve().parents[4] / "docs" / "agent-prompts" / "code_quality_agent.md"

AGENT_NAME = "code_quality"


def _load_system_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"Code Quality agent prompt not found at {PROMPT_PATH}. "
        )

    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _build_user_message(diff: str, changed_files: list[str]) -> str:
    parts = []
    if changed_files:
        parts.append("## Changed Files")
        for f in changed_files:
            parts.append(f"- {f}")
        parts.append("")

    parts.append("## Diff")
    parts.append("```diff")
    parts.append(diff)
    parts.append("```")

    return "\n".join(parts)


def _parse_findings(parsed_json: Optional[dict | list]) -> tuple[list[Finding], str]:
    if parsed_json is None:
        return [], "Failed to parse LLM response as JSON"

    if isinstance(parsed_json, list):
        raw_findings = parsed_json
        summary = ""
    elif isinstance(parsed_json, dict):
        raw_findings = parsed_json.get("findings", [])
        summary = parsed_json.get("summary", "")
    else:
        return [], "Unexpected LLM response format"

    findings = []
    for raw in raw_findings:
        try:
            severity_str = raw.get("severity", "warning").lower()
            try:
                severity = Severity(severity_str)
            except ValueError:
                severity = Severity.WARNING

            finding = Finding(
                file=raw.get("file", "unknown"),
                line=raw.get("line", 0),
                severity=severity,
                category=raw.get("category", "unknown"),
                title=raw.get("title", "Untitled finding"),
                explanation=raw.get("explanation", ""),
                suggested_fix=raw.get("suggested_fix", ""),
                confidence=raw.get("confidence", 0.8),
            )
            findings.append(finding)
        except Exception as e:
            logger.warning(f"Skipping malformed finding: {e}")
            continue

    return findings, summary


async def run(
    diff: str,
    changed_files: Optional[list[str]] = None,
    model: Optional[str] = None,
) -> AgentResult:
    changed_files = changed_files or []
    start_time = time.time()

    await emit_event("agent_started", {
        "agent": AGENT_NAME,
        "status": "scanning",
        "message": f"Code Quality Agent scanning {len(changed_files)} file(s)...",
    })

    logger.info(
        f"Code Quality Agent starting — "
        f"{len(changed_files)} files, {len(diff)} chars of diff"
    )

    try:
        system_prompt = _load_system_prompt()
        user_message = _build_user_message(diff, changed_files)

        response = await llm_client.call(
            system_prompt=system_prompt,
            user_message=user_message,
            model=model,
        )

        findings, summary = _parse_findings(response.parsed_json)
        duration = time.time() - start_time

        if not summary:
            counts = {"critical": 0, "warning": 0, "info": 0}
            for f in findings:
                counts[f.severity.value] += 1

            parts = []
            if counts["critical"]:
                parts.append(f"{counts['critical']} critical")
            if counts["warning"]:
                parts.append(f"{counts['warning']} warning")
            if counts["info"]:
                parts.append(f"{counts['info']} info")

            if parts:
                summary = f"Found {', '.join(parts)} issue(s)."
            else:
                summary = "No code quality issues found."

        result = AgentResult(
            agent_name=AGENT_NAME,
            findings=findings,
            summary=summary,
            token_usage=response.token_usage,
            duration_seconds=round(duration, 2),
        )

        await emit_event("agent_completed", {
            "agent": AGENT_NAME,
            "status": "completed",
            "findings_count": len(findings),
            "summary": summary,
            "duration": round(duration, 2),
        })

        logger.info(
            f"Code Quality Agent finished — {len(findings)} findings, "
            f"{duration:.1f}s, {response.token_usage.total_tokens} tokens"
        )

        return result

    except Exception as e:
        duration = time.time() - start_time
        error_msg = f"Code Quality Agent failed: {str(e)}"
        logger.error(error_msg)

        await emit_event("agent_completed", {
            "agent": AGENT_NAME,
            "status": "error",
            "error": str(e),
            "duration": round(duration, 2),
        })

        return AgentResult(
            agent_name=AGENT_NAME,
            findings=[],
            summary="",
            error=error_msg,
            duration_seconds=round(duration, 2),
        )
