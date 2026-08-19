"""
Parse unified diffs into structured hunks with line-number mapping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

NOISE_PATTERNS = (
    ".gitignore",
    ".antigravityignore",
    ".gitattributes",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Cargo.lock",
    ".pulse/",
)

HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class DiffHunk:
    file: str
    old_start: int
    new_start: int
    new_line_count: int
    lines: list[str] = field(default_factory=list)

    def new_line_range(self) -> tuple[int, int]:
        if self.new_line_count <= 0:
            end = self.new_start
        else:
            end = self.new_start + self.new_line_count - 1
        return self.new_start, max(self.new_start, end)


@dataclass
class ParsedDiff:
    files: list[str] = field(default_factory=list)
    hunks_by_file: dict[str, list[DiffHunk]] = field(default_factory=dict)
    added_lines: dict[str, list[tuple[int, str]]] = field(default_factory=dict)

    def line_in_diff(self, file: str, line: int, tolerance: int = 3) -> bool:
        if line <= 0:
            return True
        for hunk in self.hunks_by_file.get(file, []):
            start, end = hunk.new_line_range()
            if start - tolerance <= line <= end + tolerance:
                return True
        return False

    def get_hunks_for_file(self, file: str) -> list[DiffHunk]:
        return self.hunks_by_file.get(file, [])

    def to_dict(self) -> dict:
        return {
            "files": list(self.files),
            "hunks_by_file": {
                path: [
                    {
                        "file": h.file,
                        "old_start": h.old_start,
                        "new_start": h.new_start,
                        "new_line_count": h.new_line_count,
                        "lines": h.lines,
                    }
                    for h in hunks
                ]
                for path, hunks in self.hunks_by_file.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> ParsedDiff:
        parsed = cls(files=list(data.get("files", [])))
        for path, hunks in (data.get("hunks_by_file") or {}).items():
            parsed.hunks_by_file[path] = [
                DiffHunk(
                    file=h["file"],
                    old_start=h["old_start"],
                    new_start=h["new_start"],
                    new_line_count=h["new_line_count"],
                    lines=list(h.get("lines", [])),
                )
                for h in hunks
            ]
        return parsed


def _is_noise_file(path: str) -> bool:
    return any(pattern in path for pattern in NOISE_PATTERNS)


def _normalize_path(raw: str) -> str:
    path = raw.strip()
    if path.startswith("a/") or path.startswith("b/"):
        path = path[2:]
    return path.replace("\\", "/")


def parse_diff(diff: str) -> ParsedDiff:
    """Parse a unified diff into structured hunks."""
    parsed = ParsedDiff()
    if not diff or not diff.strip():
        return parsed

    if diff.lstrip().startswith("## File:"):
        for block in re.split(r"(?=^## File: )", diff, flags=re.MULTILINE):
            block = block.strip()
            if not block.startswith("## File:"):
                continue
            first_line, _, rest = block.partition("\n")
            file_path = first_line.replace("## File:", "").strip()
            if _is_noise_file(file_path):
                continue
            parsed.files.append(file_path)
            parsed.hunks_by_file.setdefault(file_path, [])
            parsed.added_lines.setdefault(file_path, [])
            for idx, line in enumerate(rest.splitlines(), start=1):
                parsed.added_lines[file_path].append((idx, line))
        return parsed

    current_file: Optional[str] = None
    current_hunk: Optional[DiffHunk] = None
    new_line_num = 0

    for line in diff.splitlines():
        if line.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+?) b/(.+)", line)
            if match:
                current_file = _normalize_path(match.group(2))
                if _is_noise_file(current_file):
                    current_file = None
                    current_hunk = None
                    continue
                if current_file not in parsed.files:
                    parsed.files.append(current_file)
                parsed.hunks_by_file.setdefault(current_file, [])
                parsed.added_lines.setdefault(current_file, [])
            continue

        if not current_file:
            continue

        hunk_match = HUNK_HEADER.match(line)
        if hunk_match:
            current_hunk = DiffHunk(
                file=current_file,
                old_start=int(hunk_match.group(1)),
                new_start=int(hunk_match.group(2)),
                new_line_count=0,
            )
            parsed.hunks_by_file[current_file].append(current_hunk)
            new_line_num = current_hunk.new_start
            continue

        if current_hunk is None:
            continue

        current_hunk.lines.append(line)
        if line.startswith("+") and not line.startswith("+++"):
            content = line[1:]
            parsed.added_lines[current_file].append((new_line_num, content))
            current_hunk.new_line_count += 1
            new_line_num += 1
        elif line.startswith("-") and not line.startswith("---"):
            pass
        elif line.startswith(" ") or line == "":
            new_line_num += 1

    return parsed


def format_hunks_for_file(parsed: ParsedDiff, file_path: str) -> str:
    """Format hunks for a single file as diff text for the repair agent."""
    hunks = parsed.get_hunks_for_file(file_path)
    if not hunks:
        return ""
    parts = [f"--- a/{file_path}", f"+++ b/{file_path}"]
    for hunk in hunks:
        count = max(hunk.new_line_count, 1)
        parts.append(f"@@ -{hunk.old_start},1 +{hunk.new_start},{count} @@")
        parts.extend(hunk.lines)
    return "\n".join(parts)
