"""
Pulse Orchestrator — LangGraph Review Graph

  START → prepare_context → architect → [security, performance, quality]
        → dedup (validate + deduplicate) → repair_gate → repair → END
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from langgraph.graph import StateGraph, START, END

from app.graph.state import ReviewState
from app.agents import architect_agent, security_agent, performance_agent, code_quality_agent
from app.agents.dedup import deduplicate_findings
from app.agents.repair_runner import run_repair
from app.context.context_builder import build_review_context
from app.context.diff_parser import ParsedDiff
from app.config import get_project_root
from app.models.agent_models import Severity
from app.settings_store import get_setting
from app.utils.logger import setup_logger
from app.validation.finding_validator import validate_agent_results
from app.ws.socket_server import emit_event

logger = setup_logger("pulse.graph")


async def prepare_context_node(state: ReviewState):
    """Build enriched context and parse diff before agents run."""
    diff = state.get("diff", "")
    changed_files = list(state.get("changed_files") or [])
    project_root = state.get("project_root") or get_project_root() or str(Path.cwd())

    file_context, parsed, normalized_files = build_review_context(
        diff, changed_files, project_root
    )

    return {
        "project_root": project_root,
        "file_context": file_context,
        "parsed_hunks": parsed.to_dict(),
        "changed_files": normalized_files,
    }


async def architect_node(state: ReviewState):
    routes = await architect_agent.plan_review(state["diff"], state.get("changed_files", []))
    return {"active_agents": routes}


async def security_node(state: ReviewState):
    res = await security_agent.run(
        state["diff"],
        state.get("changed_files", []),
        state.get("file_context", ""),
    )
    return {"results": [res]}


async def performance_node(state: ReviewState):
    res = await performance_agent.run(
        state["diff"],
        state.get("changed_files", []),
        state.get("file_context", ""),
    )
    return {"results": [res]}


async def quality_node(state: ReviewState):
    res = await code_quality_agent.run(
        state["diff"],
        state.get("changed_files", []),
        state.get("file_context", ""),
    )
    return {"results": [res]}


async def dedup_node(state: ReviewState):
    results = state.get("results", [])
    parsed = ParsedDiff.from_dict(state.get("parsed_hunks") or {})
    validated = validate_agent_results(
        results,
        state.get("diff", ""),
        parsed,
        state.get("changed_files", []),
    )
    deduped = deduplicate_findings(validated)
    if deduped:
        object.__setattr__(deduped[0], "_dedup_replace", True)
    return {"results": deduped}


async def repair_gate_node(state: ReviewState):
    return {}


async def repair_node(state: ReviewState):
    auto_repair = get_setting("auto_repair", True)
    if not auto_repair:
        logger.info("Auto-repair disabled in settings — skipping repair node")
        return {"repair_results": []}

    start_time = time.time()
    await emit_event("agent_started", {
        "agent": "repair",
        "status": "scanning",
        "message": "Repair Agent analyzing findings for Docker sandbox patches...",
    })

    results = state.get("results", [])
    diff = state.get("diff", "")
    changed_files = state.get("changed_files", [])
    project_root = state.get("project_root") or get_project_root()

    repair_results = []
    finding_global_index = 0
    target_findings = []
    repair_min_confidence = get_setting("repair_min_confidence", 0.7)

    for agent_result in results:
        for finding in agent_result.findings:
            if (
                finding.severity in (Severity.CRITICAL, Severity.WARNING)
                and (finding.confidence or 0.0) >= repair_min_confidence
            ):
                target_findings.append((finding, finding_global_index))
            finding_global_index += 1

    if not target_findings:
        logger.info("No critical/warning findings above confidence threshold — skipping repair")
        await emit_event("agent_completed", {
            "agent": "repair",
            "status": "completed",
            "duration": 0,
            "findings_count": 0,
            "summary": "No findings eligible for repair",
        })
        return {"repair_results": []}

    for finding, idx in target_findings:
        logger.info(f"Attempting repair for finding: '{finding.title}' in {finding.file}")
        repair_result = await run_repair(
            finding=finding,
            finding_index=idx,
            diff=diff,
            changed_files=changed_files,
            project_path=project_root,
        )
        repair_results.append(repair_result)

    duration = time.time() - start_time
    await emit_event("agent_completed", {
        "agent": "repair",
        "status": "completed",
        "duration": round(duration, 2),
        "findings_count": len(repair_results),
        "summary": f"Generated {len(repair_results)} repair patch(es)",
    })

    return {"repair_results": repair_results}


def _should_repair(state: ReviewState) -> str:
    auto_repair = get_setting("auto_repair", True)
    if not auto_repair:
        return "end"

    repair_min_confidence = get_setting("repair_min_confidence", 0.7)
    for agent_result in state.get("results", []):
        for finding in agent_result.findings:
            if (
                finding.severity in (Severity.CRITICAL, Severity.WARNING)
                and (finding.confidence or 0.0) >= repair_min_confidence
            ):
                return "repair"
    return "end"


def build_review_graph():
    builder = StateGraph(ReviewState)

    builder.add_node("prepare_context", prepare_context_node)
    builder.add_node("architect", architect_node)
    builder.add_node("security", security_node)
    builder.add_node("performance", performance_node)
    builder.add_node("quality", quality_node)
    builder.add_node("dedup", dedup_node)
    builder.add_node("repair_gate", repair_gate_node)
    builder.add_node("repair", repair_node)

    builder.add_edge(START, "prepare_context")
    builder.add_edge("prepare_context", "architect")

    def route_from_architect(state: ReviewState) -> Any:
        agents = state.get("active_agents", [])
        if not agents:
            return ["dedup"]
        return agents

    builder.add_conditional_edges(
        "architect",
        route_from_architect,
        {
            "security": "security",
            "performance": "performance",
            "quality": "quality",
            "dedup": "dedup",
        },
    )

    builder.add_edge("security", "dedup")
    builder.add_edge("performance", "dedup")
    builder.add_edge("quality", "dedup")
    builder.add_edge("dedup", "repair_gate")

    builder.add_conditional_edges(
        "repair_gate",
        _should_repair,
        {"repair": "repair", "end": END},
    )

    builder.add_edge("repair", END)

    return builder.compile()


review_graph = build_review_graph()
