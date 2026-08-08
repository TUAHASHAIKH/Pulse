"""
Pulse Orchestrator — Cross-Agent Finding Deduplication

After all reviewer agents (security, performance, quality) run in parallel,
their findings may overlap. For example, a `console.log` in production code
might be flagged by both the Performance Agent and the Code Quality Agent.

This module provides a deterministic, zero-LLM-cost deduplication step that:
  1. Compares every pair of findings across agents
  2. Marks two findings as duplicates if they share the same file,
     are within ±5 lines, and have similar titles (60%+ word overlap)
  3. Keeps the "best" version based on severity, domain ownership,
     and confidence score
  4. Returns cleaned AgentResult lists with duplicates removed

This runs as a LangGraph node between the reviewer agents and the repair gate.
"""

import re
from app.models.agent_models import AgentResult, Finding, Severity
from app.utils.logger import setup_logger

logger = setup_logger("pulse.dedup")

# ─── Constants ───

LINE_PROXIMITY = 5  # findings within ±5 lines are candidates for dedup

TITLE_SIMILARITY_THRESHOLD = 0.60  # 60% word overlap required

# Which agent "owns" which finding categories
DOMAIN_OWNERSHIP = {
    "security": {
        "sql-injection", "command-injection", "xss", "hardcoded-secret",
        "path-traversal", "insecure-auth", "unsafe-deserialization",
        "missing-validation", "insecure-dependency", "info-disclosure",
    },
    "performance": {
        "performance", "n-plus-one", "missing-index", "memory-leak",
        "inefficient-loop", "re-render",
    },
    "quality": {
        "code_quality", "dead-code", "complexity", "naming",
        "code-duplication", "anti-pattern",
    },
}

SEVERITY_RANK = {
    Severity.CRITICAL: 3,
    Severity.WARNING: 2,
    Severity.INFO: 1,
}


# ─── Similarity helpers ───


def _normalize_title(title: str) -> set[str]:
    """
    Extract significant words from a title for comparison.
    Strips common filler words and lowercases everything.
    """
    stop_words = {
        "a", "an", "the", "in", "on", "of", "to", "for", "is", "are",
        "was", "were", "be", "been", "and", "or", "not", "with", "from",
        "by", "at", "this", "that", "it", "its", "but", "as", "if",
        "no", "every", "all", "each", "can", "could", "should", "would",
        "has", "have", "had", "do", "does", "did", "will", "shall",
    }
    words = set(re.findall(r"[a-z0-9]+", title.lower()))
    return words - stop_words


def _title_similarity(title_a: str, title_b: str) -> float:
    """
    Compute word-overlap similarity between two finding titles.

    Returns a float in [0.0, 1.0]:
      - 1.0 means identical word sets
      - 0.0 means no overlap at all

    Also returns 1.0 if one title is a substring of the other,
    which catches cases like:
      "console.log on every render" vs "Unconditional console.log on every provider render"
    """
    # Substring check first
    a_lower = title_a.lower().strip()
    b_lower = title_b.lower().strip()
    if a_lower in b_lower or b_lower in a_lower:
        return 1.0

    words_a = _normalize_title(title_a)
    words_b = _normalize_title(title_b)

    if not words_a or not words_b:
        return 0.0

    intersection = words_a & words_b
    union = words_a | words_b

    return len(intersection) / len(union)


def _is_duplicate(a: Finding, b: Finding) -> bool:
    """
    Determine whether two findings are duplicates.

    Criteria (ALL must match):
      1. Same file path (exact match)
      2. Line numbers within ±LINE_PROXIMITY
      3. Title similarity >= TITLE_SIMILARITY_THRESHOLD
    """
    # 1. Same file
    if a.file != b.file:
        return False

    # 2. Line proximity
    if abs(a.line - b.line) > LINE_PROXIMITY:
        return False

    # 3. Title similarity
    similarity = _title_similarity(a.title, b.title)
    if similarity < TITLE_SIMILARITY_THRESHOLD:
        return False

    return True


def _get_domain_owner(finding: Finding) -> str | None:
    """
    Return the agent name that "owns" this finding's category,
    or None if the category doesn't map to a specific domain.
    """
    category = finding.category.lower().strip()
    for agent, categories in DOMAIN_OWNERSHIP.items():
        if category in categories:
            return agent
    return None


def _pick_winner(
    finding_a: Finding, agent_a: str,
    finding_b: Finding, agent_b: str,
) -> tuple[Finding, str]:
    """
    Given two duplicate findings from different agents, pick the one to keep.

    Priority:
      1. Higher severity wins (critical > warning > info)
      2. Domain owner wins (security finding → keep security agent's version)
      3. Higher confidence wins
      4. Tie → keep the first one
    """
    sev_a = SEVERITY_RANK.get(finding_a.severity, 0)
    sev_b = SEVERITY_RANK.get(finding_b.severity, 0)

    if sev_a != sev_b:
        return (finding_a, agent_a) if sev_a > sev_b else (finding_b, agent_b)

    # Domain ownership
    domain_owner = _get_domain_owner(finding_a)
    if domain_owner == agent_a and domain_owner != agent_b:
        return finding_a, agent_a
    if domain_owner == agent_b and domain_owner != agent_a:
        return finding_b, agent_b

    # Also check finding_b's category (they might differ)
    domain_owner_b = _get_domain_owner(finding_b)
    if domain_owner_b == agent_b and domain_owner_b != agent_a:
        return finding_b, agent_b
    if domain_owner_b == agent_a and domain_owner_b != agent_b:
        return finding_a, agent_a

    # Confidence tiebreaker
    conf_a = finding_a.confidence or 0.0
    conf_b = finding_b.confidence or 0.0
    if conf_a != conf_b:
        return (finding_a, agent_a) if conf_a > conf_b else (finding_b, agent_b)

    # Final fallback: keep the first one
    return finding_a, agent_a


def deduplicate_findings(results: list[AgentResult]) -> list[AgentResult]:
    """
    Remove duplicate findings across multiple agent results.

    Takes the list of AgentResult objects (one per agent), compares
    findings cross-agent, and returns a new list with duplicates removed.

    Findings within the SAME agent are never deduplicated (each agent
    is responsible for its own output quality).

    Returns:
        New list of AgentResult objects with duplicates removed.
        The original objects are not modified.
    """
    if len(results) <= 1:
        return results

    # Build a flat list of (finding, agent_name, agent_index, finding_index)
    all_findings: list[tuple[Finding, str, int, int]] = []
    for agent_idx, result in enumerate(results):
        for finding_idx, finding in enumerate(result.findings):
            all_findings.append((finding, result.agent_name, agent_idx, finding_idx))

    # Track which findings to remove: set of (agent_index, finding_index)
    to_remove: set[tuple[int, int]] = set()
    total_before = len(all_findings)

    # Compare every cross-agent pair
    for i in range(len(all_findings)):
        if (all_findings[i][2], all_findings[i][3]) in to_remove:
            continue

        for j in range(i + 1, len(all_findings)):
            if (all_findings[j][2], all_findings[j][3]) in to_remove:
                continue

            f_a, agent_a, ai, fi = all_findings[i]
            f_b, agent_b, aj, fj = all_findings[j]

            # Skip same-agent comparisons
            if agent_a == agent_b:
                continue

            if _is_duplicate(f_a, f_b):
                winner, winner_agent = _pick_winner(f_a, agent_a, f_b, agent_b)

                if winner is f_a:
                    to_remove.add((aj, fj))
                    logger.debug(
                        f"Dedup: keeping '{f_a.title}' from {agent_a}, "
                        f"removing duplicate from {agent_b}"
                    )
                else:
                    to_remove.add((ai, fi))
                    logger.debug(
                        f"Dedup: keeping '{f_b.title}' from {agent_b}, "
                        f"removing duplicate from {agent_a}"
                    )
                    break  # f_a was removed, stop comparing it

    # Rebuild results without removed findings
    new_results = []
    for agent_idx, result in enumerate(results):
        kept_findings = [
            f for finding_idx, f in enumerate(result.findings)
            if (agent_idx, finding_idx) not in to_remove
        ]

        new_result = AgentResult(
            agent_name=result.agent_name,
            findings=kept_findings,
            summary=result.summary,
            token_usage=result.token_usage,
            duration_seconds=result.duration_seconds,
            error=result.error,
        )
        new_results.append(new_result)

    total_after = sum(len(r.findings) for r in new_results)
    removed = total_before - total_after

    if removed > 0:
        logger.info(
            f"Dedup: removed {removed} duplicate(s) from {total_before} findings "
            f"→ {total_after} unique findings"
        )
    else:
        logger.info(f"Dedup: no duplicates found across {total_before} findings")

    return new_results
