"""
Pulse Orchestrator — Settings Store

Simple JSON-file-based persistence for user preferences.
Reads/writes from .pulse/settings.json in the project root.

Settings include:
  - fix_delivery: default fix delivery method (ask/local/pr_comment/branch)
  - auto_repair: whether to auto-repair critical findings
  - repair_max_attempts: max repair attempts per finding

This is NOT a database — just a single JSON file for user preferences.
For a production system, this would be a proper database.
"""

import json
import os
from pathlib import Path
from typing import Any, Optional

from app.config import get_project_root
from app.utils.logger import setup_logger

logger = setup_logger("pulse.settings")

# Default settings
DEFAULTS = {
    "fix_delivery": "ask",        # ask | local | pr_comment | branch
    "auto_repair": True,          # auto-run repair on critical findings
    "repair_max_attempts": 3,     # max repair attempts per finding
    "auto_review_push": False,    # auto-review code before every git push
    "block_push": True,           # ask "Continue pushing? Y/n" after review
}


def _get_settings_path() -> Path:
    """Get the path to the settings file."""
    project_root = get_project_root()
    if project_root:
        return Path(project_root) / ".pulse" / "settings.json"
    # Fallback to cwd
    return Path.cwd() / ".pulse" / "settings.json"


def load_settings() -> dict:
    """
    Load settings from .pulse/settings.json.

    Returns defaults merged with any saved values.
    Missing keys get default values.
    """
    settings = dict(DEFAULTS)
    settings_path = _get_settings_path()

    if settings_path.exists():
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            settings.update(saved)
            logger.debug(f"Settings loaded from {settings_path}")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load settings from {settings_path}: {e}")

    return settings


def save_settings(settings: dict) -> bool:
    """
    Save settings to .pulse/settings.json.

    Creates the .pulse directory if it doesn't exist.

    Returns:
        True if saved successfully, False otherwise.
    """
    settings_path = _get_settings_path()

    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)

        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)

        logger.info(f"Settings saved to {settings_path}")
        return True

    except OSError as e:
        logger.error(f"Failed to save settings to {settings_path}: {e}")
        return False


def get_setting(key: str, default: Any = None) -> Any:
    """Get a single setting value."""
    settings = load_settings()
    return settings.get(key, default)


def update_setting(key: str, value: Any) -> bool:
    """Update a single setting and save."""
    settings = load_settings()
    settings[key] = value
    return save_settings(settings)
