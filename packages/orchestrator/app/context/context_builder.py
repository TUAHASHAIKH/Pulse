"""
Build enriched file context for reviewer and repair agents.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from app.context.diff_parser import ParsedDiff, parse_diff
from app.settings_store import get_setting
from app.utils.logger import setup_logger

logger = setup_logger("pulse.context")

MAX_FILE_CHARS = 12000
MAX_CONTEXT_CHARS = 8000
MAX_FILE_LINES = 500

IMPORT_PATTERNS = [
    re.compile(r"^\s*import\s+.+$", re.MULTILINE),
    re.compile(r"^\s*from\s+\S+\s+import\s+.+$", re.MULTILINE),
    re.compile(r"^\s*require\s*\(\s*['\"].+['\"]\s*\)", re.MULTILINE),
    re.compile(r"^\s*const\s+.+\s*=\s*require\s*\(", re.MULTILINE),
]

TEST_SUFFIXES = (
    ".test.ts", ".test.tsx", ".test.js", ".test.jsx",
    ".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx",
)
TEST_PREFIXES = ("test_", "tests/test_")


def _read_file_safe(path: Path, max_lines: int = MAX_FILE_LINES) -> Optional[str]:
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            text = "\n".join(lines) + "\n... (truncated)"
        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS] + "\n... (truncated)"
        return text
    except OSError as e:
        logger.debug(f"Could not read {path}: {e}")
        return None


def _extract_imports(content: str) -> list[str]:
    imports: list[str] = []
    for pattern in IMPORT_PATTERNS:
        imports.extend(m.group(0).strip() for m in pattern.finditer(content))
    return imports[:20]


def _find_test_file(project_root: Path, file_path: str) -> Optional[Path]:
    p = Path(file_path)
    stem = p.stem
    parent = project_root / p.parent

    candidates = [
        parent / f"{stem}.test{p.suffix}",
        parent / f"{stem}.spec{p.suffix}",
        parent / "__tests__" / f"{stem}{p.suffix}",
        project_root / "tests" / f"test_{stem}.py",
        project_root / "tests" / f"{stem}_test.py",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _resolve_file(project_root: Path, file_path: str) -> Optional[Path]:
    normalized = file_path.replace("\\", "/").lstrip("/")
    direct = project_root / normalized
    if direct.is_file():
        return direct
    for match in project_root.rglob(Path(normalized).name):
        if match.is_file() and str(match.relative_to(project_root)).replace("\\", "/") == normalized:
            return match
    return None


def build_review_context(
    diff: str,
    changed_files: list[str],
    project_root: Optional[str] = None,
) -> tuple[str, ParsedDiff, list[str]]:
    """
    Build related context string, parsed diff, and normalized changed_files list.
    """
    parsed = parse_diff(diff)
    files = list(changed_files) if changed_files else list(parsed.files)

    if not project_root:
        return "", parsed, files

    root = Path(project_root)
    if not root.is_dir():
        return "", parsed, files

    parts: list[str] = []
    total_chars = 0

    parts.append("## Related Context (read-only — do NOT flag issues here unless the diff breaks them)")
    parts.append("Use this to avoid false claims about code that exists elsewhere.")
    parts.append("")

    for file_path in files[:10]:
        resolved = _resolve_file(root, file_path)
        if not resolved:
            continue

        content = _read_file_safe(resolved)
        if not content:
            continue

        imports = _extract_imports(content)
        if imports:
            block = f"### Imports in `{file_path}`\n" + "\n".join(f"- `{i}`" for i in imports)
            if total_chars + len(block) > MAX_CONTEXT_CHARS:
                break
            parts.append(block)
            parts.append("")
            total_chars += len(block)

        test_file = _find_test_file(root, file_path)
        if test_file:
            test_content = _read_file_safe(test_file, max_lines=80)
            if test_content:
                block = (
                    f"### Related test `{test_file.relative_to(root).as_posix()}`\n"
                    f"```\n{test_content}\n```"
                )
                if total_chars + len(block) > MAX_CONTEXT_CHARS:
                    break
                parts.append(block)
                parts.append("")
                total_chars += len(block)

        sibling_dir = resolved.parent
        if sibling_dir.is_dir():
            siblings = [
                p.name for p in sibling_dir.iterdir()
                if p.is_file() and p.name != resolved.name
            ][:8]
            if siblings:
                block = f"### Sibling files in `{resolved.parent.relative_to(root).as_posix()}/`\n"
                block += ", ".join(siblings)
                if total_chars + len(block) <= MAX_CONTEXT_CHARS:
                    parts.append(block)
                    parts.append("")
                    total_chars += len(block)

    if len(parts) <= 3:
        return "", parsed, files

    return "\n".join(parts), parsed, files


def read_full_file(project_root: Optional[str], file_path: str) -> Optional[str]:
    """Read full source file content for the repair agent."""
    if not project_root:
        return None
    root = Path(project_root)
    resolved = _resolve_file(root, file_path)
    if not resolved:
        return None
    return _read_file_safe(resolved, max_lines=MAX_FILE_LINES)


def read_file_slice(
    project_root: Optional[str],
    file_path: str,
    line: int,
    window: Optional[int] = None,
) -> Optional[str]:
    """Read ±window lines around a finding line."""
    if not project_root or line <= 0:
        return read_full_file(project_root, file_path)

    window = window or int(get_setting("context_window_lines", 40))
    root = Path(project_root)
    resolved = _resolve_file(root, file_path)
    if not resolved:
        return None

    try:
        lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    start = max(0, line - window - 1)
    end = min(len(lines), line + window)
    numbered = [f"{i + 1:4d}| {lines[i]}" for i in range(start, end)]
    return "\n".join(numbered)
