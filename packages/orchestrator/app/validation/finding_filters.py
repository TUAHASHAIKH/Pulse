"""
Post-parse filters applied to agent findings before dedup.
"""

from app.models.agent_models import Finding, Severity
from app.settings_store import get_setting
from app.utils.logger import setup_logger

logger = setup_logger("pulse.validation.filters")

SEVERITY_RANK = {
    Severity.CRITICAL: 3,
    Severity.WARNING: 2,
    Severity.INFO: 1,
}


def apply_post_parse_filters(findings: list[Finding], agent_name: str) -> list[Finding]:
    """
    Drop low-confidence findings and cap count per agent.
    """
    min_confidence = float(get_setting("min_confidence_threshold", 0.6))
    max_findings = int(get_setting("max_findings_per_agent", 5))

    filtered: list[Finding] = []
    for finding in findings:
        confidence = finding.confidence if finding.confidence is not None else 0.0
        if confidence < min_confidence:
            logger.debug(
                f"{agent_name}: dropped '{finding.title}' "
                f"(confidence {confidence:.2f} < {min_confidence})"
            )
            continue
        filtered.append(finding)

    if len(filtered) > max_findings:
        filtered.sort(
            key=lambda f: (
                SEVERITY_RANK.get(f.severity, 0),
                f.confidence or 0.0,
            ),
            reverse=True,
        )
        dropped = len(filtered) - max_findings
        filtered = filtered[:max_findings]
        logger.info(
            f"{agent_name}: capped findings to {max_findings} (dropped {dropped})"
        )

    return filtered
