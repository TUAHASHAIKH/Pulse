"""
Pulse Orchestrator — Finding Deduplication

After all reviewer agents (security, performance, quality) run in parallel,
their findings may overlap — both across agents AND within a single agent.
For example:
  - A `console.log` flagged by both Performance and Code Quality
  - The same `useMemo` issue flagged 3 times by the Performance Agent
    with slightly different titles

This module provides a deterministic, zero-LLM-cost deduplication step that:
  1. Compares every pair of findings (cross-agent AND within-agent)
  2. Marks two findings as duplicates if they share the same file,
     are within ±5 lines, AND either:
     a. Have similar titles (40%+ word overlap), OR
     b. Have similar suggested fixes (targeting the same code)
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

TITLE_SIMILARITY_THRESHOLD = 0.40  # 40% word overlap required

FIX_SIMILARITY_THRESHOLD = 0.50  # 50% word overlap in suggested_fix

HIGH_FIX_SIMILARITY_THRESHOLD = 0.80  # 80% fix overlap → bypass line proximity check

CODE_IDENT_SIMILARITY_THRESHOLD = 0.50  # 50% code-identifier overlap → bypass line check

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


def _fix_similarity(fix_a: str, fix_b: str) -> float:
    """
    Compare two suggested_fix strings by extracting significant code tokens.

    This catches cases where titles are completely different but the fixes
    target the exact same code (e.g., both changing `[search, category]`
    to `[debouncedSearch, category]`).
    """
    if not fix_a or not fix_b:
        return 0.0

    # Extract code-like tokens (identifiers, operators)
    tokens_a = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", fix_a))
    tokens_b = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", fix_b))

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b

    return len(intersection) / len(union)


def _extract_code_identifiers(finding: Finding) -> set[str]:
    """
    Extract code-specific identifiers from a finding's title, explanation,
    and suggested_fix.

    Pulls out camelCase, PascalCase, and snake_case tokens that represent
    actual variable/function/class names. These are much more specific
    than generic English words and serve as a strong dedup signal.

    For example, from "useMemo dependency array omits debouncedSearch":
      → {'useMemo', 'debouncedSearch'}
    """
    combined = " ".join(filter(None, [
        finding.title,
        finding.explanation,
        finding.suggested_fix,
    ]))

    # Match camelCase, PascalCase, snake_case identifiers (min 2 chars)
    # camelCase/PascalCase: at least one lowercase followed by uppercase
    camel = set(re.findall(r'\b[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*\b', combined))
    # PascalCase: starts uppercase, has lowercase
    pascal = set(re.findall(r'\b[A-Z][a-z][a-zA-Z0-9]*\b', combined))
    # snake_case: word_word
    snake = set(re.findall(r'\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b', combined))

    # Combine all code identifiers
    idents = camel | pascal | snake

    # Filter out common English words that happen to match PascalCase
    noise = {
        'The', 'This', 'That', 'Each', 'Every', 'More', 'Change',
        'Fixed', 'Updated', 'Moved', 'Added', 'Removed', 'Used',
        'Instead', 'While', 'After', 'Before', 'Inside', 'Also',
        'Combined', 'Causing', 'Running', 'Using', 'Importantly',
        'Expensive', 'Memoize', 'Reduce', 'Compute', 'Ensure', 'Ensuring',
        'Actually', 'Raw', 'State', 'Update', 'Value', 'Array', 'Incorrectly',
        'Downstream', 'Pipeline', 'Aggregate', 'Nested', 'Loop', 'Outer', 'Inner',
        'Filter', 'Sort', 'Map', 'Object', 'Function', 'Return', 'Callback',
    }
    idents -= noise

    return idents


def _code_ident_similarity(a: Finding, b: Finding) -> float:
    """
    Compare the code identifiers mentioned in two findings.

    If both findings mention the same variable/function names
    (e.g., 'debouncedSearch', 'useMemo'), they're very likely
    about the same issue even if their titles are worded differently.
    """
    idents_a = _extract_code_identifiers(a)
    idents_b = _extract_code_identifiers(b)

    if not idents_a or not idents_b:
        return 0.0

    intersection = idents_a & idents_b
    union = idents_a | idents_b

    return len(intersection) / len(union)


def _is_duplicate(a: Finding, b: Finding) -> bool:
    """
    Determine whether two findings are duplicates.

    Three-tier criteria:

    Tier 1 (strong signal — bypasses line check):
      Same file + high suggested_fix similarity (>= 80%)

    Tier 2 (code identity — bypasses line check):
      Same file + high code-identifier overlap (>= 50%)
      Catches cases where LLMs describe the same useMemo/debouncedSearch
      issue with completely different English prose.

    Tier 3 (standard check):
      Same file + line proximity (±5) + at least ONE of:
        a. Title similarity >= 40%
        b. Suggested fix similarity >= 50%
    """
    # Must be the same file
    if a.file != b.file:
        return False

    # Tier 1: Near-identical fixes → always duplicate regardless of line distance
    fix_sim = _fix_similarity(a.suggested_fix or "", b.suggested_fix or "")
    if fix_sim >= HIGH_FIX_SIMILARITY_THRESHOLD:
        return True

    # Tier 2: Same code identifiers → same underlying issue
    ident_sim = _code_ident_similarity(a, b)
    if ident_sim >= CODE_IDENT_SIMILARITY_THRESHOLD:
        return True

    # Tier 3: Line proximity required
    if abs(a.line - b.line) > LINE_PROXIMITY:
        return False

    # 3a. Title similarity
    title_sim = _title_similarity(a.title, b.title)
    if title_sim >= TITLE_SIMILARITY_THRESHOLD:
        return True

    # 3b. Moderate fix similarity
    if fix_sim >= FIX_SIMILARITY_THRESHOLD:
        return True

    return False


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


def _is_file_deletion(finding: Finding) -> bool:
    """Detect if a finding suggests removing or deleting the entire file."""
    text = (finding.title + " " + (finding.suggested_fix or "")).lower()
    has_remove = bool(re.search(r'\b(remove|removed|removes|removing|delete|deleted|deletes|deleting)\b', text))
    has_file = bool(re.search(r'\b(file|page|route)\b', text))
    return has_remove and has_file


def _merge_findings(a: Finding, b: Finding) -> Finding:
    """Merge two nearby findings into a Compound Finding."""
    sev_a = SEVERITY_RANK.get(a.severity, 0)
    sev_b = SEVERITY_RANK.get(b.severity, 0)
    merged_severity = a.severity if sev_a > sev_b else b.severity
    
    new_title = a.title if a.title.startswith("Multiple Issues") else f"Multiple Issues: {a.title} & {b.title}"
    if len(new_title) > 120:
        new_title = new_title[:117] + "..."

    # If it's already a compound finding, append without numbering
    prefix_a = "" if a.title.startswith("Multiple Issues") else "1) "
    prefix_b = "" if b.title.startswith("Multiple Issues") else ("2) " if not a.title.startswith("Multiple Issues") else "- ")

    return Finding(
        file=a.file,
        line=min(a.line, b.line),
        severity=merged_severity,
        category=a.category,
        title=new_title,
        explanation=f"{prefix_a}{a.explanation}\n\n{prefix_b}{b.explanation}",
        suggested_fix=f"{prefix_a}{a.suggested_fix}\n\n{prefix_b}{b.suggested_fix}",
        confidence=min(a.confidence or 0.0, b.confidence or 0.0)
    )


def deduplicate_findings(results: list[AgentResult]) -> list[AgentResult]:
    """
    Remove duplicate findings and merge conflicting findings across multiple agent results.

    Three-Stage Conflict Resolution:
      1. File-Level Subsumption: If a finding removes a file, discard all other findings for that file.
      2. Semantic Duplicates: Deduplicate same-issue findings (based on code-idents/fixes).
      3. Context-Overlap Merging: Combine different issues within 15 lines into one patch.
    """
    if not results:
        return results

    # Build a dict grouping findings by file:
    # {file_path: list of (finding, agent_name, agent_idx, finding_idx)}
    findings_by_file: dict[str, list[tuple[Finding, str, int, int]]] = {}
    total_before = 0
    for agent_idx, result in enumerate(results):
        for finding_idx, finding in enumerate(result.findings):
            findings_by_file.setdefault(finding.file, []).append(
                (finding, result.agent_name, agent_idx, finding_idx)
            )
            total_before += 1

    to_remove: set[tuple[int, int]] = set()
    new_findings_by_agent: dict[int, list[Finding]] = {i: [] for i in range(len(results))}

    for file_path, file_findings in findings_by_file.items():
        if not file_findings:
            continue

        # --- Stage 2: File-Level Subsumption ---
        deletion_finding = None
        for f_tuple in file_findings:
            if _is_file_deletion(f_tuple[0]):
                deletion_finding = f_tuple
                break

        if deletion_finding:
            # Keep the deletion, discard all other findings for this file
            for f_tuple in file_findings:
                if f_tuple != deletion_finding:
                    if f_tuple[3] != -1:
                        to_remove.add((f_tuple[2], f_tuple[3]))
                    logger.debug(f"Dedup: '{f_tuple[0].title}' subsumed by file deletion '{deletion_finding[0].title}'")
            continue  # Skip Stage 1 and 3 for this file

        # --- Stage 1 & 3: Semantic Duplicates & Context-Overlap Merging ---
        active = list(file_findings)
        changed = True
        while changed:
            changed = False
            for i in range(len(active)):
                if changed: break
                for j in range(i + 1, len(active)):
                    f_a, agent_a, ai, fi = active[i]
                    f_b, agent_b, aj, fj = active[j]

                    if _is_duplicate(f_a, f_b):
                        # Stage 1: Semantic duplicate
                        winner, winner_agent = _pick_winner(f_a, agent_a, f_b, agent_b)
                        if winner is f_a:
                            if fj != -1: to_remove.add((aj, fj))
                            active.pop(j)
                            logger.debug(f"Dedup: keeping '{f_a.title}', removing duplicate '{f_b.title}'")
                        else:
                            if fi != -1: to_remove.add((ai, fi))
                            active.pop(i)
                            logger.debug(f"Dedup: keeping '{f_b.title}', removing duplicate '{f_a.title}'")
                        changed = True
                        break

                    elif (
                        abs(f_a.line - f_b.line) <= 15
                        and f_a.category.lower().strip() == f_b.category.lower().strip()
                    ):
                        # Stage 3: Context-Overlap Merging (same category only)
                        merged_f = _merge_findings(f_a, f_b)
                        if fi != -1: to_remove.add((ai, fi))
                        if fj != -1: to_remove.add((aj, fj))
                        
                        target_agent_idx = ai if fi != -1 else (aj if fj != -1 else 0)
                        
                        active.pop(j)
                        active.pop(i)
                        
                        # Add the compound finding. fi = -1 denotes it is synthesized.
                        active.append((merged_f, agent_a, target_agent_idx, -1))
                        logger.debug(f"Dedup: merged overlapping findings into '{merged_f.title}'")
                        changed = True
                        break

        # Collect any synthesized findings from this file
        for f, agent_name, agent_idx, finding_idx in active:
            if finding_idx == -1:
                new_findings_by_agent[agent_idx].append(f)

    # Rebuild results without removed findings, and append new compound findings
    new_results = []
    total_after = 0
    for agent_idx, result in enumerate(results):
        kept_findings = [
            f for finding_idx, f in enumerate(result.findings)
            if (agent_idx, finding_idx) not in to_remove
        ]
        kept_findings.extend(new_findings_by_agent[agent_idx])
        total_after += len(kept_findings)

        new_result = AgentResult(
            agent_name=result.agent_name,
            findings=kept_findings,
            summary=result.summary,
            token_usage=result.token_usage,
            duration_seconds=result.duration_seconds,
            error=result.error,
        )
        new_results.append(new_result)

    removed = total_before - total_after
    if removed > 0:
        logger.info(
            f"Dedup: consolidated/removed {removed} finding(s) from {total_before} findings "
            f"→ {total_after} unique/merged findings"
        )
    else:
        logger.info(f"Dedup: no overlaps found across {total_before} findings")

    return new_results
