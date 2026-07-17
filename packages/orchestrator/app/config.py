"""
Pulse Orchestrator — Configuration

Configuration priority (highest wins):
  1. Environment variables     — for CI/CD and power users
  2. .pulse/config.json        — from `pulse init` (main path for most users)
  3. .env file                 — fallback for local dev
  4. Defaults                  — sensible fallbacks for optional settings

The .pulse/config.json file is created by `pulse init` and lives in
the project root. It is gitignored so API keys are never committed.
End users never need to touch a .env file — `pulse init` handles
everything through a friendly interactive wizard.
"""

import json
import os
from pathlib import Path
from typing import Any, Optional

from pydantic_settings import BaseSettings
from pydantic import Field


def _find_pulse_config() -> Optional[dict]:
    """
    Walk up from the current working directory to find .pulse/config.json.

    This mimics how tools like .gitignore, package.json, and tsconfig.json
    are discovered — start where you are, walk up until you find it or
    hit the filesystem root.

    Returns:
        The parsed config dict, or None if no config file was found.
    """
    current = Path.cwd()

    # Walk up the directory tree
    for directory in [current, *current.parents]:
        config_path = directory / ".pulse" / "config.json"
        if config_path.is_file():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                # Store where we found it, so other modules can reference it
                config["_config_path"] = str(config_path)
                config["_project_root"] = str(directory)
                return config
            except (json.JSONDecodeError, OSError):
                # Malformed or unreadable config — skip it
                return None

    return None


def _merge_pulse_config_into_env(pulse_config: dict) -> None:
    """
    Inject values from .pulse/config.json into the environment,
    but ONLY if they aren't already set.

    This gives us the priority chain:
      env vars (already set) > .pulse/config.json > .env > defaults

    The key mapping is:
      config.json key  →  environment variable
      ─────────────────────────────────────────
      llm_api_key      →  LLM_API_KEY
      llm_provider     →  LLM_PROVIDER
      github_token     →  GITHUB_TOKEN
      webhook_secret   →  GITHUB_WEBHOOK_SECRET
      ...etc (any key maps to its UPPER_CASE equivalent)
    """
    # Map of config.json keys → env var names
    # This allows config.json to use friendly names while
    # the env vars stay consistent with .env.example
    KEY_MAP = {
        "llm_api_key": "LLM_API_KEY",
        "llm_provider": "LLM_PROVIDER",
        "github_token": "GITHUB_TOKEN",
        "github_webhook_secret": "GITHUB_WEBHOOK_SECRET",
        "github_app_id": "GITHUB_APP_ID",
        "github_private_key_path": "GITHUB_PRIVATE_KEY_PATH",
        "orchestrator_port": "ORCHESTRATOR_PORT",
        "dashboard_port": "DASHBOARD_PORT",
        "dashboard_origin": "DASHBOARD_ORIGIN",
        "log_level": "LOG_LEVEL",
    }

    for config_key, env_var in KEY_MAP.items():
        if config_key in pulse_config and env_var not in os.environ:
            os.environ[env_var] = str(pulse_config[config_key])


# ─── Load .pulse/config.json (if it exists) before Settings reads env ───

_pulse_config = _find_pulse_config()
if _pulse_config:
    _merge_pulse_config_into_env(_pulse_config)


class Settings(BaseSettings):
    """
    All configuration for the Pulse orchestrator.

    Values are resolved in priority order:
      1. Environment variables (highest)
      2. .pulse/config.json (injected into env before this class loads)
      3. .env file
      4. Defaults defined here (lowest)
    """

    # ─── GitHub ───
    github_webhook_secret: str = Field(
        default="",
        description="Secret used to verify incoming GitHub webhook signatures"
    )
    github_token: str = Field(
        default="",
        description="GitHub Personal Access Token for API access (posting PR comments, fetching diffs)"
    )
    github_app_id: str = Field(
        default="",
        description="GitHub App ID (alternative to PAT, better for teams)"
    )
    github_private_key_path: str = Field(
        default="",
        description="Path to the GitHub App private key PEM file"
    )

    # ─── LLM ───
    llm_api_key: str = Field(
        default="",
        description="API key for the LLM provider (Anthropic, OpenAI, or Groq)"
    )
    llm_provider: str = Field(
        default="anthropic",
        description="LLM provider to use: 'anthropic', 'openai', or 'groq'"
    )

    # ─── Server ───
    orchestrator_port: int = Field(
        default=8000,
        description="Port the FastAPI server listens on"
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR"
    )

    # ─── Dashboard ───
    dashboard_port: int = Field(
        default=3000,
        description="Port the Next.js dashboard runs on"
    )
    dashboard_origin: str = Field(
        default="http://localhost:3000",
        description="CORS origin for the Next.js dashboard"
    )

    # ─── Metadata (set automatically, not by the user) ───
    config_source: str = Field(
        default="defaults",
        description="Where the config was loaded from (for logging)"
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# ─── Build the singleton ───

settings = Settings()

# Tag the config source for the startup banner
if _pulse_config:
    settings.config_source = f".pulse/config.json ({_pulse_config.get('_project_root', 'unknown')})"
elif os.path.exists(".env"):
    settings.config_source = ".env file"
else:
    settings.config_source = "defaults + environment variables"


def get_pulse_config_path() -> Optional[str]:
    """
    Returns the path to the .pulse/config.json that was loaded,
    or None if no config file was found.
    Useful for `pulse init` to know if config already exists.
    """
    if _pulse_config:
        return _pulse_config.get("_config_path")
    return None


def get_project_root() -> Optional[str]:
    """
    Returns the project root directory (where .pulse/ lives),
    or None if no config file was found.
    """
    if _pulse_config:
        return _pulse_config.get("_project_root")
    return None
