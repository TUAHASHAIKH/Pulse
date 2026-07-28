"""
Pulse Orchestrator — Prompt Path Resolver

Resolves paths to agent system prompts across different environments:
  - Local monorepo development (repo_root/docs/agent-prompts/)
  - Standalone bundled CLI/npm package (app/prompts/)
  - Docker container / production installations
"""

from pathlib import Path


def get_prompt_path(agent_name: str) -> Path:
    """
    Locates the markdown system prompt for a given agent across various
    installation layouts.

    Args:
        agent_name: Name of the agent (e.g., 'security', 'performance', 'code_quality', 'repair')

    Returns:
        Path object pointing to the markdown prompt file.
    """
    filename = f"{agent_name}_agent.md"
    current_file = Path(__file__).resolve()

    # 1. First check inside app/prompts/ (packaged bundle layout in npm / Docker / standalone)
    candidate_app = current_file.parents[1] / "prompts" / filename
    if candidate_app.exists():
        return candidate_app

    # 2. Check parent directories up to 6 levels up for docs/agent-prompts/ (monorepo layout)
    for i in range(1, len(current_file.parents)):
        candidate_docs = current_file.parents[i] / "docs" / "agent-prompts" / filename
        if candidate_docs.exists():
            return candidate_docs

    # 3. Fallback to app/prompts/ candidate so any Error message is descriptive
    return candidate_app
