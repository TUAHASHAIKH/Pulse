"""
Pulse Orchestrator — State Tracker

Tracks which files have been scanned by Pulse and their SHA-256 hashes.
Persists state to `.pulse/state.json` in the project root.

This enables two key features:
  1. Full Audit Mode — scan an entire existing repository
  2. Incremental Audit — skip files that haven't changed since last scan

Design decisions:
  - Uses SHA-256 hashes (not git SHAs) so it works independently of git history
  - Respects .gitignore via `git ls-files` for file discovery
  - Skips binary files silently (only counts source code files)
  - Files larger than MAX_FILE_SIZE_BYTES are skipped to avoid LLM overload
  - State file lives in .pulse/ which is already gitignored by `pulse init`
"""

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import get_project_root
from app.utils.logger import setup_logger

logger = setup_logger("pulse.state")

# ─── Constants ───

MAX_FILE_SIZE_BYTES = 100 * 1024  # 100 KB — skip files larger than this
STATE_SCHEMA_VERSION = 1

# File extensions to consider as source code (everything else is silently skipped)
SOURCE_EXTENSIONS = {
    # Python
    ".py", ".pyi",
    # JavaScript / TypeScript
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    # Web
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".vue", ".svelte",
    # Data / Config
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env",
    # Markup
    ".md", ".mdx", ".txt", ".rst",
    # JVM
    ".java", ".kt", ".kts", ".scala", ".groovy",
    # Systems
    ".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cs", ".go", ".rs", ".zig",
    # Ruby / PHP / Perl
    ".rb", ".php", ".pl", ".pm",
    # Shell
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    # SQL
    ".sql",
    # Swift / Objective-C
    ".swift", ".m", ".mm",
    # Dart / Flutter
    ".dart",
    # Elixir / Erlang
    ".ex", ".exs", ".erl",
    # Haskell / OCaml / F#
    ".hs", ".ml", ".fs", ".fsx",
    # R / Julia / Lua
    ".r", ".jl", ".lua",
    # Docker / Infra
    ".dockerfile",
    # XML
    ".xml", ".xsl", ".xsd",
    # GraphQL / Protobuf
    ".graphql", ".gql", ".proto",
}

# Directory names to always skip (even if not in .gitignore)
SKIP_DIRS = {
    ".git", ".pulse", "node_modules", "__pycache__", ".venv", "venv",
    ".env", "dist", "build", ".next", ".nuxt", ".svelte-kit",
    "coverage", ".pytest_cache", ".mypy_cache", ".tox",
    "vendor", "target", "bin", "obj",
}


# ─── File Discovery ───


def _is_source_file(path: Path) -> bool:
    """Check if a file should be treated as scannable source code."""
    return path.suffix.lower() in SOURCE_EXTENSIONS


def _should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped entirely."""
    return dirname in SKIP_DIRS


def collect_project_files(project_root: str) -> list[Path]:
    """
    Collect all source code files in the project.

    Strategy:
      1. Try `git ls-files` first (respects .gitignore automatically)
      2. Fall back to manual directory walk if not a git repo

    Returns a list of absolute Path objects for scannable source files.
    Binary files, lockfiles, and files in SKIP_DIRS are excluded silently.
    """
    root = Path(project_root).resolve()
    files: list[Path] = []

    # Try git ls-files first (respects .gitignore)
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            for rel_path in result.stdout.strip().split("\n"):
                abs_path = root / rel_path
                if abs_path.is_file() and _is_source_file(abs_path):
                    # Also check none of the parent dirs are in SKIP_DIRS
                    parts = Path(rel_path).parts
                    if not any(_should_skip_dir(p) for p in parts):
                        files.append(abs_path)
            logger.info(f"Collected {len(files)} source files via git ls-files")
            return sorted(files)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning(f"git ls-files failed, falling back to manual walk: {e}")

    # Fallback: manual directory walk
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped directories in-place
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

        for filename in filenames:
            filepath = Path(dirpath) / filename
            if _is_source_file(filepath):
                files.append(filepath)

    logger.info(f"Collected {len(files)} source files via directory walk")
    return sorted(files)


# ─── Hashing ───


def file_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ─── State Persistence ───


def _get_state_path() -> Path:
    """Get the path to .pulse/state.json."""
    project_root = get_project_root()
    if project_root:
        return Path(project_root) / ".pulse" / "state.json"
    return Path.cwd() / ".pulse" / "state.json"


def load_state() -> dict:
    """
    Load scan state from .pulse/state.json.

    Returns a dict with schema:
    {
        "schema_version": 1,
        "last_scan": "2026-08-07T14:30:00Z",
        "scan_mode": "full",
        "files": {
            "src/auth.ts": {
                "sha256": "...",
                "scanned_at": "...",
                "findings_count": 0,
                "status": "clean"
            }
        }
    }
    """
    state_path = _get_state_path()
    if state_path.exists():
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.debug(f"State loaded from {state_path} ({len(data.get('files', {}))} files tracked)")
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load state from {state_path}: {e}")

    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "last_scan": None,
        "scan_mode": None,
        "files": {},
    }


def save_state(state: dict) -> bool:
    """Save scan state to .pulse/state.json."""
    state_path = _get_state_path()
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        logger.info(f"State saved to {state_path} ({len(state.get('files', {}))} files tracked)")
        return True
    except OSError as e:
        logger.error(f"Failed to save state: {e}")
        return False


def update_file_state(
    state: dict,
    rel_path: str,
    sha256: str,
    findings_count: int,
) -> None:
    """Update the state entry for a single file after scanning."""
    state["files"][rel_path] = {
        "sha256": sha256,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "findings_count": findings_count,
        "status": "clean" if findings_count == 0 else "has_findings",
    }


# ─── Scan Planning ───


def get_files_needing_scan(
    project_root: str,
    force_full: bool = False,
) -> tuple[list[Path], dict]:
    """
    Determine which files need scanning.

    Args:
        project_root: Path to the project root directory
        force_full: If True, scan all files regardless of state

    Returns:
        Tuple of:
          - List of absolute file paths that need scanning
          - Stats dict with keys: files_total, files_to_scan, files_skipped, files_oversized
    """
    root = Path(project_root).resolve()
    all_files = collect_project_files(project_root)
    state = load_state()
    file_states = state.get("files", {})

    to_scan: list[Path] = []
    skipped = 0
    oversized = 0

    for filepath in all_files:
        # Check file size
        try:
            size = filepath.stat().st_size
        except OSError:
            continue

        if size > MAX_FILE_SIZE_BYTES:
            oversized += 1
            logger.debug(f"Skipping oversized file ({size} bytes): {filepath.name}")
            continue

        if force_full:
            to_scan.append(filepath)
            continue

        # Check against saved state
        rel_path = str(filepath.relative_to(root)).replace("\\", "/")
        current_hash = file_sha256(filepath)
        prev = file_states.get(rel_path)

        if prev is not None and prev.get("sha256") == current_hash:
            skipped += 1
        else:
            to_scan.append(filepath)

    stats = {
        "files_total": len(all_files),
        "files_to_scan": len(to_scan),
        "files_skipped": skipped,
        "files_oversized": oversized,
    }

    logger.info(
        f"Scan plan: {stats['files_to_scan']} to scan, "
        f"{stats['files_skipped']} unchanged (skipped), "
        f"{stats['files_oversized']} oversized (skipped), "
        f"{stats['files_total']} total"
    )

    return to_scan, stats


def read_file_content(filepath: Path) -> Optional[str]:
    """
    Read a source file's content as a string.

    Returns None if the file can't be read (binary content, encoding issues, etc.)
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError as e:
        logger.warning(f"Failed to read {filepath}: {e}")
        return None


def build_file_content_payload(
    files: list[Path],
    project_root: str,
) -> list[tuple[str, str]]:
    """
    Build (relative_path, content) pairs for a list of files.

    Reads each file and returns a list of tuples suitable for
    constructing the LLM user message.
    """
    root = Path(project_root).resolve()
    pairs: list[tuple[str, str]] = []

    for filepath in files:
        content = read_file_content(filepath)
        if content is not None:
            rel_path = str(filepath.relative_to(root)).replace("\\", "/")
            pairs.append((rel_path, content))

    return pairs


def batch_files_by_size(
    file_pairs: list[tuple[str, str]],
    max_chars_per_batch: int = 80_000,
) -> list[list[tuple[str, str]]]:
    """
    Split file content pairs into batches that fit within LLM context limits.

    Each batch is a list of (rel_path, content) tuples whose combined
    character count stays under max_chars_per_batch.
    """
    batches: list[list[tuple[str, str]]] = []
    current_batch: list[tuple[str, str]] = []
    current_size = 0

    for rel_path, content in file_pairs:
        file_size = len(content) + len(rel_path) + 50  # overhead for formatting

        # If a single file exceeds the limit, it gets its own batch
        if file_size > max_chars_per_batch:
            if current_batch:
                batches.append(current_batch)
                current_batch = []
                current_size = 0
            batches.append([(rel_path, content)])
            continue

        if current_size + file_size > max_chars_per_batch:
            batches.append(current_batch)
            current_batch = []
            current_size = 0

        current_batch.append((rel_path, content))
        current_size += file_size

    if current_batch:
        batches.append(current_batch)

    return batches
