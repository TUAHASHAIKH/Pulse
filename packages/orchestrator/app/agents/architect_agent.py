"""
Pulse Orchestrator — Architect Agent

Rules-based routing to skip irrelevant reviewer agents.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from app.utils.logger import setup_logger

logger = setup_logger("pulse.agent.architect")

DOC_EXTENSIONS = {".md", ".markdown", ".txt", ".rst"}
CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
ASSET_EXTENSIONS = {".css", ".scss", ".sass", ".less", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2"}
LOCKFILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Cargo.lock", "go.sum",
}
TEST_PATTERNS = (".test.", ".spec.", "_test.", "test_", "/tests/", "/__tests__/")
SENSITIVE_PATTERNS = (".env", "secret", "credential", "auth", "login", "password", "token")


def _ext(path: str) -> str:
    return Path(path).suffix.lower()


def _basename(path: str) -> str:
    return Path(path).name.lower()


def _is_test_file(path: str) -> bool:
    lower = path.lower().replace("\\", "/")
    return any(p in lower for p in TEST_PATTERNS)


def _is_sensitive_path(path: str) -> bool:
    lower = path.lower().replace("\\", "/")
    return any(p in lower for p in SENSITIVE_PATTERNS)


async def plan_review(diff: str, changed_files: List[str]) -> List[str]:
    """
    Determine which reviewer agents should run based on changed file types.
    """
    logger.info(f"Architect Agent analyzing {len(changed_files)} file(s) for routing.")

    if not diff or not diff.strip():
        logger.warning("Architect Agent received empty diff — skipping reviewers.")
        return []

    if not changed_files:
        logger.info("Architect Agent dispatching to all reviewers (no file list).")
        return ["security", "performance", "quality"]

    file_kinds: dict[str, set[str]] = {}
    for path in changed_files:
        kinds: set[str] = set()
        ext = _ext(path)
        base = _basename(path)

        if base in LOCKFILES:
            kinds.add("lock")
        if ext in DOC_EXTENSIONS:
            kinds.add("doc")
        if ext in CONFIG_EXTENSIONS and base not in LOCKFILES:
            kinds.add("config")
        if ext in ASSET_EXTENSIONS:
            kinds.add("asset")
        if _is_test_file(path):
            kinds.add("test")
        if _is_sensitive_path(path):
            kinds.add("sensitive")
        if not kinds or kinds <= {"config"}:
            if ext not in DOC_EXTENSIONS | ASSET_EXTENSIONS:
                kinds.add("code")

        file_kinds[path] = kinds

    all_kinds = set().union(*file_kinds.values()) if file_kinds else {"code"}

    if all_kinds <= {"doc", "lock", "config"}:
        logger.info("Architect: docs/config/lockfiles only — skipping all reviewers.")
        return []

    routes: list[str] = []
    assets_only = all_kinds <= {"asset", "doc", "config", "lock"}
    test_only = all_kinds <= {"test", "doc", "config", "lock"} and "code" not in all_kinds
    has_code = "code" in all_kinds or "sensitive" in all_kinds

    if not assets_only:
        routes.append("security")

    if test_only:
        pass
    elif not (all_kinds <= {"doc", "config", "lock", "asset"}):
        routes.append("performance")

    if has_code or "test" in all_kinds or "sensitive" in all_kinds or not assets_only:
        routes.append("quality")

    routes = list(dict.fromkeys(routes))

    logger.info(f"Architect Agent dispatching to: {', '.join(routes) or 'none'}")
    return routes
