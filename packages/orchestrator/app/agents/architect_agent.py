"""
Pulse Orchestrator — Architect Agent

The Architect Agent acts as the central coordinator in the LangGraph workflow.
It receives the raw diff and test results, determines which specialist agents
need to be invoked, and prepares the routing state.

In future phases, this agent could use an LLM to dynamically decide whether
to skip certain agents (e.g., skipping the Performance agent if only markdown
files were changed). For now, it parses the input and dispatches to all
active reviewer agents.
"""

from typing import List
from app.utils.logger import setup_logger

logger = setup_logger("pulse.agent.architect")

async def plan_review(diff: str, changed_files: List[str]) -> List[str]:
    """
    Parses the incoming diff and determines which agents should review it.
    
    Args:
        diff: The unified diff string
        changed_files: List of file paths that were changed
        
    Returns:
        A list of agent node names to route to.
    """
    logger.info(f"Architect Agent analyzing diff ({len(changed_files)} files) to determine review routes.")
    
    # In a fully dynamic setup, we might call an LLM here to analyze the files.
    # For Phase 3, we want to fan out to all three primary reviewer agents to 
    # demonstrate the parallel LangGraph capability.
    
    routes = []
    
    # Simple deterministic routing logic:
    # If there's a diff, we always run security, performance, and code quality.
    if diff and diff.strip():
        routes.extend(["security", "performance", "quality"])
        logger.info(f"Architect Agent dispatching to: {', '.join(routes)}")
    else:
        logger.warning("Architect Agent received empty diff. Skipping reviewer agents.")
        
    return routes
