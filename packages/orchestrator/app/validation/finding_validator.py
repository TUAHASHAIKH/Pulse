"""
Post-agent validation gate — rejects hallucinated or out-of-domain findings.
"""

from __future__ import annotations

from app.context.diff_parser import ParsedDiff
from app.models.agent_models import AgentResult, Finding
from app.settings_store import get_setting
from app.utils.logger import setup_logger

logger = setup_logger("pulse.validation.findings")

AGENT_ALLOWED_CATEGORIES: dict[str, set[str]] = {
    "security": {
        "sql-injection", "command-injection", "xss", "hardcoded-secret",
        "path-traversal", "insecure-auth", "unsafe-deserialization",
        "missing-validation", "insecure-dependency", "info-disclosure",
        "security",
    },
    "performance": {
        "performance", "n-plus-one", "missing-index", "memory-leak",
        "inefficient-loop", "re-render",
    },
    "code_quality": {
        "code_quality", "dead-code", "complexity", "naming",
        "code-duplication", "anti-pattern",
    },
}


def _evidence_in_diff(finding: Finding, diff: str, parsed: ParsedDiff, changed_files: list[str]) -> bool:
    evidence = (finding.evidence or "").strip()
    if not evidence:
        return not get_setting("strict_evidence_validation", True)

    # Strip markdown code blocks/backticks
    if evidence.startswith("```") and evidence.endswith("```"):
        evidence = "\n".join(evidence.split("\n")[1:-1]).strip()
    evidence = evidence.strip("`").strip()

    # Normalize by removing all leading '+' and spaces on EVERY line
    evidence_lines = [line.lstrip("+").strip() for line in evidence.split("\n") if line.strip()]
    if not evidence_lines:
        return False

    # Check against raw diff
    diff_lines = [line.lstrip("+").strip() for line in diff.split("\n") if line.strip()]
    
    # Simple check: are all non-empty evidence lines found somewhere in the diff?
    all_found_in_diff = all(any(e_line in d_line for d_line in diff_lines) for e_line in evidence_lines)
    if all_found_in_diff:
        return True

    # Fallback to checking parsed hunks, resolving file name if it's just a basename
    actual_file = finding.file
    if actual_file not in parsed.added_lines:
        for f in parsed.added_lines:
            if f.endswith(actual_file) or actual_file.endswith(f.split("/")[-1]):
                actual_file = f
                break
                
    added_contents = [content.strip() for _, content in parsed.added_lines.get(actual_file, [])]
    
    # Are all evidence lines found in the added lines of the correct file?
    all_found_in_added = all(any(e_line in a_line for a_line in added_contents) for e_line in evidence_lines)
    return all_found_in_added


def validate_finding(
    finding: Finding,
    agent_name: str,
    diff: str,
    parsed: ParsedDiff,
    changed_files: list[str],
) -> tuple[bool, str]:
    min_confidence = float(get_setting("min_confidence_threshold", 0.6))
    confidence = finding.confidence if finding.confidence is not None else 0.0

    if confidence < min_confidence:
        return False, f"confidence {confidence:.2f} below threshold"

    if changed_files and finding.file not in changed_files:
        basename_match = any(
            finding.file.endswith(f.split("/")[-1]) or f.endswith(finding.file.split("/")[-1])
            for f in changed_files
        )
        if not basename_match:
            return False, f"file '{finding.file}' not in changed files"

    if finding.line > 0 and not parsed.line_in_diff(finding.file, finding.line):
        return False, f"line {finding.line} not within any diff hunk for {finding.file}"

    allowed = AGENT_ALLOWED_CATEGORIES.get(agent_name)
    if allowed and finding.category.lower().strip() not in allowed:
        return False, f"category '{finding.category}' out of domain for {agent_name}"

    if not _evidence_in_diff(finding, diff, parsed, changed_files):
        return False, "evidence not found in diff"

    return True, ""


def validate_agent_results(
    results: list[AgentResult],
    diff: str,
    parsed: ParsedDiff,
    changed_files: list[str],
) -> list[AgentResult]:
    """Filter invalid findings from each agent result."""
    validated: list[AgentResult] = []

    for result in results:
        kept: list[Finding] = []
        for finding in result.findings:
            ok, reason = validate_finding(
                finding, result.agent_name, diff, parsed, changed_files
            )
            if ok:
                kept.append(finding)
            else:
                logger.info(
                    f"Rejected finding '{finding.title}' from {result.agent_name}: {reason}"
                )

        validated.append(
            AgentResult(
                agent_name=result.agent_name,
                findings=kept,
                summary=result.summary,
                token_usage=result.token_usage,
                duration_seconds=result.duration_seconds,
                error=result.error,
            )
        )

    return validated
