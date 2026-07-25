"""
Pulse Orchestrator — LangGraph Review Graph

Defines the agent execution graph:

  START → architect → [security, performance, quality] → repair_gate → repair → END
                                                              │
                                                              └─(no criticals)→ END

The graph coordinates:
  1. Architect Agent decides which reviewers to run
  2. Reviewer agents run in parallel (fan-out)
  3. Repair gate checks if any critical findings exist
  4. Repair node generates and tests fixes for critical findings
"""

from typing import Any
from langgraph.graph import StateGraph, START, END
from app.graph.state import ReviewState
from app.agents import architect_agent, security_agent, performance_agent, code_quality_agent
from app.agents.repair_runner import run_repair
from app.models.agent_models import Severity, RepairResult
from app.settings_store import get_setting
from app.utils.logger import setup_logger

logger = setup_logger("pulse.graph")


async def architect_node(state: ReviewState):
    """The central coordinator that decides which agents to run."""
    routes = await architect_agent.plan_review(state["diff"], state["changed_files"])
    return {"active_agents": routes}

async def security_node(state: ReviewState):
    res = await security_agent.run(state["diff"], state["changed_files"])
    return {"results": [res]}

async def performance_node(state: ReviewState):
    res = await performance_agent.run(state["diff"], state["changed_files"])
    return {"results": [res]}

async def quality_node(state: ReviewState):
    res = await code_quality_agent.run(state["diff"], state["changed_files"])
    return {"results": [res]}


async def repair_gate_node(state: ReviewState):
    """
    Check if any critical findings exist that need repair.

    This is a pass-through node — it doesn't modify state.
    It exists solely to provide a routing decision point.
    """
    # Just pass through — routing logic is in the conditional edge
    return {}


async def repair_node(state: ReviewState):
    """
    Run the Repair Agent on all critical findings.

    For each critical finding across all agent results, attempts
    to generate and verify a fix in the Docker sandbox.
    """
    auto_repair = get_setting("auto_repair", True)
    if not auto_repair:
        logger.info("Auto-repair disabled in settings — skipping repair node")
        return {"repair_results": []}

    results = state.get("results", [])
    diff = state.get("diff", "")
    changed_files = state.get("changed_files", [])

    repair_results = []
    finding_global_index = 0

    for agent_result in results:
        for finding in agent_result.findings:
            if finding.severity == Severity.CRITICAL:
                logger.info(
                    f"Attempting repair for critical finding: "
                    f"'{finding.title}' in {finding.file}"
                )

                repair_result = await run_repair(
                    finding=finding,
                    finding_index=finding_global_index,
                    diff=diff,
                    changed_files=changed_files,
                )
                repair_results.append(repair_result)

            finding_global_index += 1

    return {"repair_results": repair_results}


def _should_repair(state: ReviewState) -> str:
    """Route to repair if any critical findings exist, otherwise END."""
    results = state.get("results", [])

    for agent_result in results:
        for finding in agent_result.findings:
            if finding.severity == Severity.CRITICAL:
                logger.info("Critical findings detected — routing to repair agent")
                return "repair"

    logger.info("No critical findings — skipping repair agent")
    return "end"


def build_review_graph():
    builder = StateGraph(ReviewState)

    # ── Nodes ──
    builder.add_node("architect", architect_node)
    builder.add_node("security", security_node)
    builder.add_node("performance", performance_node)
    builder.add_node("quality", quality_node)
    builder.add_node("repair_gate", repair_gate_node)
    builder.add_node("repair", repair_node)

    # 1. Start always goes to the Architect
    builder.add_edge(START, "architect")

    # 2. Architect dynamically routes to the chosen reviewer agents
    def route_from_architect(state: ReviewState) -> Any:
        return state.get("active_agents", [])

    builder.add_conditional_edges(
        "architect",
        route_from_architect,
        {
            "security": "security",
            "performance": "performance",
            "quality": "quality",
        }
    )

    # 3. All reviewer agents fan-in to the repair gate
    builder.add_edge("security", "repair_gate")
    builder.add_edge("performance", "repair_gate")
    builder.add_edge("quality", "repair_gate")

    # 4. Repair gate decides whether to repair or skip to END
    builder.add_conditional_edges(
        "repair_gate",
        _should_repair,
        {
            "repair": "repair",
            "end": END,
        }
    )

    # 5. Repair node goes to END
    builder.add_edge("repair", END)

    return builder.compile()

# Global compiled graph instance
review_graph = build_review_graph()
