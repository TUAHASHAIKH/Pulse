"""
Pulse Orchestrator — Code Quality Agent
"""

from typing import Optional

from app.agents.base_reviewer import BaseReviewer
from app.models.agent_models import AgentResult

AGENT_NAME = "code_quality"
_reviewer = BaseReviewer(AGENT_NAME, "code_quality")


async def run(
    diff: str,
    changed_files: Optional[list[str]] = None,
    file_context: str = "",
    model: Optional[str] = None,
) -> AgentResult:
    return await _reviewer.run(diff, changed_files, file_context, model)
