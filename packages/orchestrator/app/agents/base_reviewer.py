"""
Shared reviewer agent logic for security, performance, and code quality agents.
"""

from __future__ import annotations

import time
from typing import Optional

from app.integrations.llm_client import llm_client
from app.models.agent_models import AgentResult, Finding, Severity
from app.utils.logger import setup_logger
from app.utils.prompts import get_prompt_path
from app.validation.finding_filters import apply_post_parse_filters
from app.ws.socket_server import emit_event

logger = setup_logger("pulse.agent.base")


class BaseReviewer:
    def __init__(self, agent_name: str, prompt_key: str):
        self.agent_name = agent_name
        self.prompt_key = prompt_key

    def _load_system_prompt(self) -> str:
        prompt_path = get_prompt_path(self.prompt_key)
        if not prompt_path.exists():
            raise FileNotFoundError(
                f"{self.agent_name} agent prompt not found at {prompt_path}"
            )
        return prompt_path.read_text(encoding="utf-8")

    def _build_user_message(
        self,
        diff: str,
        changed_files: list[str],
        file_context: str = "",
    ) -> str:
        is_full_file = diff.lstrip().startswith("## File:")
        parts: list[str] = []

        if file_context:
            parts.append(file_context)
            parts.append("")

        if changed_files:
            header = "## Files Under Review" if is_full_file else "## Changed Files"
            parts.append(header)
            for f in changed_files:
                parts.append(f"- {f}")
            parts.append("")

        if is_full_file:
            parts.append("## Source Files")
            parts.append(diff)
        else:
            parts.append("## Diff")
            parts.append("```diff")
            parts.append(diff)
            parts.append("```")

        return "\n".join(parts)

    def _parse_findings(self, parsed_json: Optional[dict | list]) -> tuple[list[Finding], str]:
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

        findings: list[Finding] = []
        for raw in raw_findings:
            try:
                severity_str = raw.get("severity", "warning").lower()
                try:
                    severity = Severity(severity_str)
                except ValueError:
                    severity = Severity.WARNING

                findings.append(
                    Finding(
                        file=raw.get("file", "unknown"),
                        line=raw.get("line", 0),
                        severity=severity,
                        category=raw.get("category", "unknown"),
                        title=raw.get("title", "Untitled finding"),
                        explanation=raw.get("explanation", ""),
                        suggested_fix=raw.get("suggested_fix", ""),
                        confidence=raw.get("confidence", 0.8),
                        evidence=raw.get("evidence", ""),
                    )
                )
            except Exception as e:
                logger.warning(f"Skipping malformed finding: {e}")

        return findings, summary

    def _build_summary(self, findings: list[Finding], summary: str) -> str:
        if summary:
            return summary
        counts = {"critical": 0, "warning": 0, "info": 0}
        for f in findings:
            counts[f.severity.value] = counts.get(f.severity.value, 0) + 1
        parts = []
        if counts["critical"]:
            parts.append(f"{counts['critical']} critical")
        if counts["warning"]:
            parts.append(f"{counts['warning']} warning")
        if counts["info"]:
            parts.append(f"{counts['info']} info")
        if parts:
            return f"Found {', '.join(parts)} issue(s)."
        return f"No {self.agent_name} issues found."

    async def run(
        self,
        diff: str,
        changed_files: Optional[list[str]] = None,
        file_context: str = "",
        model: Optional[str] = None,
    ) -> AgentResult:
        changed_files = changed_files or []
        start_time = time.time()

        await emit_event("agent_started", {
            "agent": self.agent_name,
            "status": "scanning",
            "message": f"{self.agent_name.title()} Agent scanning {len(changed_files)} file(s)...",
        })

        logger.info(
            f"{self.agent_name.title()} Agent starting — "
            f"{len(changed_files)} files, {len(diff)} chars of diff"
        )

        try:
            system_prompt = self._load_system_prompt()
            user_message = self._build_user_message(diff, changed_files, file_context)

            response = await llm_client.call(
                system_prompt=system_prompt,
                user_message=user_message,
                model=model,
            )

            findings, summary = self._parse_findings(response.parsed_json)
            findings = apply_post_parse_filters(findings, self.agent_name)
            summary = self._build_summary(findings, summary)
            duration = time.time() - start_time

            result = AgentResult(
                agent_name=self.agent_name,
                findings=findings,
                summary=summary,
                token_usage=response.token_usage,
                duration_seconds=round(duration, 2),
            )

            await emit_event("agent_completed", {
                "agent": self.agent_name,
                "status": "completed",
                "findings_count": len(findings),
                "summary": summary,
                "duration": round(duration, 2),
            })

            logger.info(
                f"{self.agent_name.title()} Agent finished — {len(findings)} findings, "
                f"{duration:.1f}s, {response.token_usage.total_tokens} tokens"
            )
            return result

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"{self.agent_name.title()} Agent failed: {str(e)}"
            logger.error(error_msg)

            await emit_event("agent_completed", {
                "agent": self.agent_name,
                "status": "error",
                "error": str(e),
                "duration": round(duration, 2),
            })

            return AgentResult(
                agent_name=self.agent_name,
                findings=[],
                summary="",
                error=error_msg,
                duration_seconds=round(duration, 2),
            )
