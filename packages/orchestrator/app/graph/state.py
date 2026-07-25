from typing import TypedDict, List
import operator
from typing_extensions import Annotated
from app.models.agent_models import AgentResult, RepairResult

class ReviewState(TypedDict):
    """
    State shared across all nodes in the LangGraph execution.
    """
    diff: str
    changed_files: List[str]
    # Annotated with operator.add so parallel nodes can append to the same list without overwriting
    results: Annotated[List[AgentResult], operator.add]
    # List of agent nodes that the Architect decides to route to
    active_agents: List[str]
    # Repair results from the Repair Agent (Phase 4)
    repair_results: Annotated[List[RepairResult], operator.add]

