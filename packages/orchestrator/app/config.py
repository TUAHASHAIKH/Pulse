"""
Pulse Orchestrator — Configuration

Reads all settings from environment variables (or a .env file).
Uses Pydantic Settings so every config value is validated at startup,
not discovered as a KeyError at 2am.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """
    All configuration for the Pulse orchestrator.
    Values are read from environment variables or a .env file.
    """

    # ─── GitHub ───
    github_webhook_secret: str = Field(
        default="",
        description="Secret used to verify incoming GitHub webhook signatures"
    )
    github_app_id: str = Field(
        default="",
        description="GitHub App ID (used in later phases for API auth)"
    )
    github_private_key_path: str = Field(
        default="",
        description="Path to the GitHub App private key PEM file"
    )

    # ─── LLM ───
    llm_api_key: str = Field(
        default="",
        description="API key for the LLM provider (Anthropic or OpenAI)"
    )
    llm_provider: str = Field(
        default="anthropic",
        description="LLM provider to use: 'anthropic' or 'openai'"
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
    dashboard_origin: str = Field(
        default="http://localhost:3000",
        description="CORS origin for the Next.js dashboard"
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# Singleton — import this everywhere
settings = Settings()
