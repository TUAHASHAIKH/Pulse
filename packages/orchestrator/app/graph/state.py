from typing import TypedDict, List
import operator
from typing_extensions import Annotated
from app.models.agent_models import AgentResult, RepairResult


def _results_reducer(existing: List[AgentResult], new: List[AgentResult]) -> List[AgentResult]:
    """
    Custom reducer for the results list.

    - If any item in `new` has `_dedup_replace` attribute set to True,
      treat the entire `new` list as a full replacement (from dedup node).
    - Otherwise, append (normal agent fan-in behavior).
    """
    if new and getattr(new[0], "_dedup_replace", False):
        # Strip the sentinel before returning
        for r in new:
            try:
                delattr(r, "_dedup_replace")
            except Exception:
                pass
        return list(new)
    return list(existing) + list(new)


class ReviewState(TypedDict):
    """
    State shared across all nodes in the LangGraph execution.
    """
    diff: str
    changed_files: List[str]
    # Custom reducer: agents append, dedup replaces
    results: Annotated[List[AgentResult], _results_reducer]
    # List of agent nodes that the Architect decides to route to
    active_agents: List[str]
    # Repair results from the Repair Agent (Phase 4)
    repair_results: Annotated[List[RepairResult], operator.add]

