"""
Lightweight static syntax checker for Python, JavaScript, JSON, etc.
Assists the Code Quality Agent by identifying deterministic parser errors.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.utils.logger import setup_logger

logger = setup_logger("pulse.context.syntax_checker")


@dataclass
class SyntaxIssue:
    file: str
    line: int
    message: str
    evidence: str = ""
    error_type: str = "SyntaxError"


def check_python_syntax(content: str, filename: str) -> list[SyntaxIssue]:
    """Check Python code using built-in compile / ast.parse."""
    issues: list[SyntaxIssue] = []
    try:
        compile(content, filename, "exec")
    except SyntaxError as e:
        line = e.lineno or 1
        snippet = (e.text or "").strip()
        if not snippet and content:
            lines = content.splitlines()
            if 0 < line <= len(lines):
                snippet = lines[line - 1].strip()
        issues.append(
            SyntaxIssue(
                file=filename,
                line=line,
                message=f"{type(e).__name__}: {e.msg}",
                evidence=snippet,
                error_type=type(e).__name__,
            )
        )
    except Exception as e:
        logger.debug(f"Python syntax check exception on {filename}: {e}")
    return issues


def check_json_syntax(content: str, filename: str) -> list[SyntaxIssue]:
    """Check JSON syntax using standard json.loads."""
    issues: list[SyntaxIssue] = []
    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        lines = content.splitlines()
        line = e.lineno
        snippet = lines[line - 1].strip() if 0 < line <= len(lines) else ""
        issues.append(
            SyntaxIssue(
                file=filename,
                line=line,
                message=f"JSONDecodeError: {e.msg}",
                evidence=snippet,
                error_type="JSONDecodeError",
            )
        )
    return issues


def check_js_syntax(content: str, filename: str) -> list[SyntaxIssue]:
    """
    Check JavaScript syntax using `node --check` if node is available.
    """
    issues: list[SyntaxIssue] = []
    node_bin = shutil.which("node")
    if not node_bin:
        return _check_delimiters(content, filename)

    ext = Path(filename).suffix.lower()
    if ext not in {".js", ".mjs", ".cjs"}:
        # TypeScript or JSX requires transpiler, fallback to delimiter check
        return _check_delimiters(content, filename)

    suffix = ext if ext else ".js"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        proc = subprocess.run(
            [node_bin, "--check", tmp_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if proc.returncode != 0:
            stderr = proc.stderr or proc.stdout or ""
            # Parse Node's output: e.g., tmp_path:12\n  code\nSyntaxError: Unexpected token
            match = re.search(r":(\d+)\r?\n([^\n]+)?\r?\n.*?(SyntaxError:[^\n]+)", stderr)
            if match:
                line = int(match.group(1))
                snippet = (match.group(2) or "").strip()
                msg = match.group(3).strip()
                issues.append(
                    SyntaxIssue(
                        file=filename,
                        line=line,
                        message=msg,
                        evidence=snippet,
                        error_type="SyntaxError",
                    )
                )
            else:
                # General syntax error fallback
                first_line = stderr.strip().splitlines()[-1] if stderr.strip() else "Syntax error"
                issues.append(
                    SyntaxIssue(
                        file=filename,
                        line=1,
                        message=first_line,
                        evidence="",
                        error_type="SyntaxError",
                    )
                )
    except Exception as e:
        logger.debug(f"Node syntax check failed: {e}")
        return _check_delimiters(content, filename)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    return issues


def _check_delimiters(content: str, filename: str) -> list[SyntaxIssue]:
    """Lightweight fallback checker for unclosed/mismatched brackets and braces."""
    pairs = {"(": ")", "{": "}", "[": "]"}
    reverse_pairs = {")": "(", "}": "{", "]": "["}
    stack: list[tuple[str, int]] = []  # (char, line_no)

    in_line_comment = False
    in_block_comment = False
    in_single_quote = False
    in_double_quote = False
    in_backtick = False

    lines = content.splitlines()
    for line_idx, line in enumerate(lines, start=1):
        in_line_comment = False
        i = 0
        n = len(line)
        while i < n:
            ch = line[i]
            # Handle comments
            if not in_single_quote and not in_double_quote and not in_backtick:
                if not in_block_comment and i + 1 < n and line[i:i+2] == "//":
                    in_line_comment = True
                    break
                if not in_block_comment and i + 1 < n and line[i:i+2] == "/*":
                    in_block_comment = True
                    i += 2
                    continue
                if in_block_comment and i + 1 < n and line[i:i+2] == "*/":
                    in_block_comment = False
                    i += 2
                    continue

            if in_block_comment or in_line_comment:
                i += 1
                continue

            # Handle strings
            if ch == "\\" and (in_single_quote or in_double_quote or in_backtick):
                i += 2
                continue

            if ch == "'" and not in_double_quote and not in_backtick:
                in_single_quote = not in_single_quote
            elif ch == '"' and not in_single_quote and not in_backtick:
                in_double_quote = not in_double_quote
            elif ch == '`' and not in_single_quote and not in_double_quote:
                in_backtick = not in_backtick
            elif not in_single_quote and not in_double_quote and not in_backtick:
                if ch in pairs:
                    stack.append((ch, line_idx))
                elif ch in reverse_pairs:
                    expected = reverse_pairs[ch]
                    if not stack:
                        return [
                            SyntaxIssue(
                                file=filename,
                                line=line_idx,
                                message=f"SyntaxError: Unmatched closing delimiter '{ch}'",
                                evidence=line.strip(),
                                error_type="SyntaxError",
                            )
                        ]
                    top_ch, top_line = stack.pop()
                    if top_ch != expected:
                        return [
                            SyntaxIssue(
                                file=filename,
                                line=line_idx,
                                message=f"SyntaxError: Mismatched delimiter: expected '{pairs[top_ch]}' to match '{top_ch}' on line {top_line}, but found '{ch}'",
                                evidence=line.strip(),
                                error_type="SyntaxError",
                            )
                        ]
            i += 1

    if in_backtick:
        return [
            SyntaxIssue(
                file=filename,
                line=len(lines),
                message="SyntaxError: Unterminated template literal (unclosed backtick)",
                evidence=lines[-1].strip() if lines else "",
                error_type="SyntaxError",
            )
        ]

    if stack:
        unclosed_ch, unclosed_line = stack[-1]
        line_content = lines[unclosed_line - 1].strip() if 0 < unclosed_line <= len(lines) else ""
        return [
            SyntaxIssue(
                file=filename,
                line=unclosed_line,
                message=f"SyntaxError: Unclosed delimiter '{unclosed_ch}' (missing closing '{pairs[unclosed_ch]}')",
                evidence=line_content,
                error_type="SyntaxError",
            )
        ]

    return []


def check_syntax_for_file(content: str, filename: str) -> list[SyntaxIssue]:
    """Dispatch syntax check based on file extension."""
    if not content or not content.strip():
        return []

    ext = Path(filename).suffix.lower()
    if ext == ".py":
        return check_python_syntax(content, filename)
    elif ext == ".json":
        return check_json_syntax(content, filename)
    elif ext in {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"}:
        return check_js_syntax(content, filename)

    return []
