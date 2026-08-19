"""
Pulse Orchestrator — Security Agent
"""

from typing import Optional

from app.agents.base_reviewer import BaseReviewer
from app.models.agent_models import AgentResult

AGENT_NAME = "security"
_reviewer = BaseReviewer(AGENT_NAME, "security")


async def run(
    diff: str,
    changed_files: Optional[list[str]] = None,
    file_context: str = "",
    model: Optional[str] = None,
) -> AgentResult:
    return await _reviewer.run(diff, changed_files, file_context, model)
