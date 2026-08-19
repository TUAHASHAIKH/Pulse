"""Unit tests for agent quality improvements."""

import asyncio

import pytest

from app.context.diff_parser import parse_diff
from app.models.agent_models import Finding, Severity, AgentResult
from app.validation.finding_validator import validate_finding
from app.agents.dedup import deduplicate_findings, _is_duplicate
from app.validation.finding_filters import apply_post_parse_filters


SAMPLE_DIFF = """diff --git a/src/auth.py b/src/auth.py
index 1111111..2222222 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,3 +10,4 @@ def login(user_email, password):
-    query = "SELECT * FROM users WHERE email = %s"
-    cursor.execute(query, (user_email,))
+    query = f"SELECT * FROM users WHERE email = '{user_email}'"
+    cursor.execute(query)
+    API_KEY = "sk-live-1234567890"
"""


def test_parse_diff_extracts_files_and_lines():
    parsed = parse_diff(SAMPLE_DIFF)
    assert "src/auth.py" in parsed.files
    assert parsed.line_in_diff("src/auth.py", 12)
    assert len(parsed.added_lines.get("src/auth.py", [])) >= 2


def test_validate_finding_rejects_missing_evidence_when_strict():
    parsed = parse_diff(SAMPLE_DIFF)
    finding = Finding(
        file="src/auth.py",
        line=12,
        severity=Severity.CRITICAL,
        category="sql-injection",
        title="SQL injection",
        explanation="Unsafe f-string in query",
        suggested_fix="Use parameterized query",
        confidence=0.95,
        evidence="",
    )
    ok, reason = validate_finding(
        finding, "security", SAMPLE_DIFF, parsed, ["src/auth.py"]
    )
    assert ok is False
    assert "evidence" in reason


def test_validate_finding_accepts_valid_evidence():
    parsed = parse_diff(SAMPLE_DIFF)
    finding = Finding(
        file="src/auth.py",
        line=12,
        severity=Severity.CRITICAL,
        category="sql-injection",
        title="SQL injection",
        explanation="Unsafe f-string in query",
        suggested_fix="Use parameterized query",
        confidence=0.95,
        evidence='query = f"SELECT * FROM users WHERE email = \'{user_email}\'"',
    )
    ok, _ = validate_finding(
        finding, "security", SAMPLE_DIFF, parsed, ["src/auth.py"]
    )
    assert ok is True


def test_deduplicate_removes_cross_agent_duplicates():
    finding_a = Finding(
        file="src/auth.py",
        line=12,
        severity=Severity.WARNING,
        category="performance",
        title="console.log on every render",
        explanation="Logs every render",
        suggested_fix="Remove console.log",
        confidence=0.8,
        evidence="console.log(user)",
    )
    finding_b = Finding(
        file="src/auth.py",
        line=12,
        severity=Severity.INFO,
        category="naming",
        title="Unconditional console.log on every render",
        explanation="Noisy logging",
        suggested_fix="Delete console.log",
        confidence=0.75,
        evidence="console.log(user)",
    )
    assert _is_duplicate(finding_a, finding_b)

    results = [
        AgentResult(agent_name="performance", findings=[finding_a], summary=""),
        AgentResult(agent_name="code_quality", findings=[finding_b], summary=""),
    ]
    deduped = deduplicate_findings(results)
    total = sum(len(r.findings) for r in deduped)
    assert total == 1


def test_architect_skips_docs_only():
    from app.agents import architect_agent

    routes = asyncio.run(
        architect_agent.plan_review("diff content", ["README.md", "CHANGELOG.md"])
    )
    assert routes == []


def test_apply_post_parse_filters_caps_findings():
    findings = [
        Finding(
            file=f"f{i}.py",
            line=i,
            severity=Severity.INFO,
            category="naming",
            title=f"issue {i}",
            explanation="x",
            confidence=0.9 - i * 0.01,
        )
        for i in range(8)
    ]
    filtered = apply_post_parse_filters(findings, "code_quality")
    assert len(filtered) <= 5


def test_parse_patch_hunks_and_apply_to_content():
    from app.agents.fix_applicator import _parse_patch_hunks, _apply_hunks_to_content

    patch = """--- a/src/auth.py
+++ b/src/auth.py
@@ -1,3 +1,3 @@
 def login():
-    password = "secret"
+    password = os.getenv("PASSWORD")
     return True
"""
    hunks = _parse_patch_hunks(patch)
    assert "src/auth.py" in hunks

    original = 'def login():\n    password = "secret"\n    return True\n'
    ok, updated, err = _apply_hunks_to_content(original, hunks["src/auth.py"])
    assert ok is True, err
    assert 'os.getenv("PASSWORD")' in updated
    assert '"secret"' not in updated
