"""
Unit tests for syntax error detection, validation, and domain ownership.
"""

import pytest

from app.context.diff_parser import parse_diff
from app.context.syntax_checker import (
    check_python_syntax,
    check_json_syntax,
    check_syntax_for_file,
    _check_delimiters,
)
from app.models.agent_models import Finding, Severity, AgentResult
from app.validation.finding_validator import validate_finding
from app.agents.dedup import _get_domain_owner, deduplicate_findings


SAMPLE_DIFF_WITH_SYNTAX_ERROR = """diff --git a/src/utils.py b/src/utils.py
index 1111111..2222222 100644
--- a/src/utils.py
+++ b/src/utils.py
@@ -10,3 +10,4 @@ def calculate_total(items):
-    return sum(item.price for item in items)
+    for item in items
+        total += item.price
+    return total
"""


def test_validate_finding_accepts_syntax_error_for_code_quality():
    parsed = parse_diff(SAMPLE_DIFF_WITH_SYNTAX_ERROR)
    finding = Finding(
        file="src/utils.py",
        line=10,
        severity=Severity.CRITICAL,
        category="syntax-error",
        title="Python SyntaxError: missing colon after for statement",
        explanation="The for loop statement is missing a trailing colon, causing SyntaxError.",
        suggested_fix="for item in items:",
        confidence=0.98,
        evidence="for item in items",
    )
    ok, reason = validate_finding(
        finding, "code_quality", SAMPLE_DIFF_WITH_SYNTAX_ERROR, parsed, ["src/utils.py"]
    )
    assert ok is True, f"Expected finding to be accepted, but got: {reason}"


def test_validate_finding_rejects_syntax_error_for_wrong_agent():
    parsed = parse_diff(SAMPLE_DIFF_WITH_SYNTAX_ERROR)
    finding = Finding(
        file="src/utils.py",
        line=10,
        severity=Severity.CRITICAL,
        category="syntax-error",
        title="Syntax error",
        explanation="broken",
        confidence=0.9,
        evidence="for item in items",
    )
    ok, reason = validate_finding(
        finding, "security", SAMPLE_DIFF_WITH_SYNTAX_ERROR, parsed, ["src/utils.py"]
    )
    assert ok is False
    assert "out of domain" in reason


def test_syntax_error_domain_ownership():
    finding = Finding(
        file="src/utils.py",
        line=10,
        severity=Severity.CRITICAL,
        category="syntax-error",
        title="SyntaxError",
        explanation="broken",
    )
    owner = _get_domain_owner(finding)
    assert owner in ("quality", "code_quality")


def test_python_syntax_checker_catches_missing_colon():
    bad_python = "def calculate_total(items)\n    return 42\n"
    issues = check_python_syntax(bad_python, "test.py")
    assert len(issues) == 1
    assert issues[0].line == 1
    assert "SyntaxError" in issues[0].message
    assert issues[0].error_type == "SyntaxError"


def test_python_syntax_checker_catches_indentation_error():
    bad_python = "def hello():\nprint('bad indent')\n"
    issues = check_python_syntax(bad_python, "test.py")
    assert len(issues) == 1
    assert "IndentationError" in issues[0].message


def test_python_syntax_checker_passes_clean_code():
    clean_python = "def calculate_total(items):\n    return sum(items)\n"
    issues = check_python_syntax(clean_python, "test.py")
    assert len(issues) == 0


def test_json_syntax_checker_catches_trailing_comma():
    bad_json = '{\n  "key": "value",\n}\n'
    issues = check_json_syntax(bad_json, "config.json")
    assert len(issues) == 1
    assert issues[0].line >= 2
    assert "JSONDecodeError" in issues[0].message


def test_delimiter_checker_catches_unclosed_brace():
    bad_js = "function test() {\n  if (true) {\n    console.log('hi');\n}\n"
    issues = _check_delimiters(bad_js, "app.js")
    assert len(issues) == 1
    assert "Unclosed delimiter" in issues[0].message


def test_check_syntax_for_file_dispatcher():
    bad_code = "def foo()\n  pass"
    issues = check_syntax_for_file(bad_code, "my_file.py")
    assert len(issues) == 1
    assert "SyntaxError" in issues[0].message
