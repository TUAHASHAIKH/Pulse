"""
Pulse Orchestrator — Agent Result Formatter

Converts an AgentResult into formatted Markdown for different outputs:
  - GitHub PR comments
  - Terminal output (CLI)
  - Dashboard display

Each agent's findings are formatted the same way — consistent
experience regardless of which agent produced them.
"""

from app.models.agent_models import AgentResult, Finding, Severity


# Severity → emoji mapping
SEVERITY_ICONS = {
    Severity.CRITICAL: "🔴",
    Severity.WARNING: "🟡",
    Severity.INFO: "🔵",
}

SEVERITY_LABELS = {
    Severity.CRITICAL: "Critical",
    Severity.WARNING: "Warning",
    Severity.INFO: "Info",
}


def format_as_github_comment(results: list[AgentResult]) -> str:
    """
    Format one or more AgentResults as a GitHub PR comment.

    Produces a clean, scannable Markdown comment that groups
    findings by severity and includes suggested fixes.
    """
    sections = []

    # Header
    sections.append("## 🫀 Pulse Code Review\n")

    # Aggregate stats across all agents
    total_findings = sum(len(r.findings) for r in results)
    total_critical = sum(
        1 for r in results for f in r.findings if f.severity == Severity.CRITICAL
    )
    total_warnings = sum(
        1 for r in results for f in r.findings if f.severity == Severity.WARNING
    )
    total_info = sum(
        1 for r in results for f in r.findings if f.severity == Severity.INFO
    )

    if total_findings == 0:
        sections.append("✅ **No issues found.** Your code looks good!\n")
        sections.append(_format_footer(results))
        return "\n".join(sections)

    # Summary bar
    summary_parts = []
    if total_critical:
        summary_parts.append(f"🔴 {total_critical} critical")
    if total_warnings:
        summary_parts.append(f"🟡 {total_warnings} warning")
    if total_info:
        summary_parts.append(f"🔵 {total_info} info")
    sections.append(f"**{total_findings} issue(s) found:** {' · '.join(summary_parts)}\n")

    # Findings grouped by agent
    for result in results:
        if not result.findings:
            continue

        agent_label = result.agent_name.replace("_", " ").title()
        sections.append(f"### {agent_label} Agent\n")

        # Sort by severity: critical first
        sorted_findings = sorted(
            result.findings,
            key=lambda f: ["critical", "warning", "info"].index(f.severity.value),
        )

        for finding in sorted_findings:
            sections.append(_format_finding(finding))

    # Footer
    sections.append(_format_footer(results))

    return "\n".join(sections)


def _format_finding(finding: Finding) -> str:
    """Format a single finding as Markdown."""
    icon = SEVERITY_ICONS.get(finding.severity, "⚪")
    label = SEVERITY_LABELS.get(finding.severity, "Unknown")

    lines = []
    lines.append(f"#### {icon} {label}: {finding.title}")
    lines.append(f"**File:** `{finding.file}` (line {finding.line})")
    lines.append("")
    lines.append(f"**Issue:** {finding.explanation}")
    lines.append("")

    if finding.suggested_fix:
        lines.append("<details>")
        lines.append("<summary>💡 Suggested Fix</summary>")
        lines.append("")
        lines.append("```")
        lines.append(finding.suggested_fix)
        lines.append("```")
        lines.append("</details>")
        lines.append("")

    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def _format_footer(results: list[AgentResult]) -> str:
    """Format the footer with metadata."""
    total_tokens = sum(r.token_usage.total_tokens for r in results)
    total_duration = sum(r.duration_seconds for r in results)
    agent_names = ", ".join(
        r.agent_name.replace("_", " ").title() + " Agent" for r in results
    )

    return (
        f"\n---\n"
        f"*Reviewed by Pulse {agent_names} · "
        f"{total_duration:.1f}s · "
        f"{total_tokens:,} tokens*"
    )


def format_as_terminal(results: list[AgentResult]) -> str:
    """
    Format results for terminal/CLI output.

    Uses ANSI colors and simpler formatting than the GitHub version.
    """
    lines = []
    lines.append("\n  Pulse Security Review")
    lines.append("  " + "=" * 40)

    total_findings = sum(len(r.findings) for r in results)

    if total_findings == 0:
        lines.append("  ✅ No issues found. Your code looks good!")
        return "\n".join(lines)

    for result in results:
        for finding in result.findings:
            icon = SEVERITY_ICONS.get(finding.severity, "⚪")
            lines.append("")
            lines.append(f"  {icon} [{finding.severity.value.upper()}] {finding.title}")
            lines.append(f"     File: {finding.file}:{finding.line}")
            lines.append(f"     {finding.explanation}")
            if finding.suggested_fix:
                lines.append(f"     Fix: {finding.suggested_fix[:100]}...")

    lines.append("")
    lines.append(f"  {total_findings} issue(s) found.")
    lines.append("")

    return "\n".join(lines)
