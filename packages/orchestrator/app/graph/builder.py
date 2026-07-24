from typing import Any
from langgraph.graph import StateGraph, START, END
from app.graph.state import ReviewState
from app.agents import architect_agent, security_agent, performance_agent, code_quality_agent

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

def build_review_graph():
    builder = StateGraph(ReviewState)

    builder.add_node("architect", architect_node)
    builder.add_node("security", security_node)
    builder.add_node("performance", performance_node)
    builder.add_node("quality", quality_node)

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

    # 3. All reviewer agents fan-in to END
    builder.add_edge("security", END)
    builder.add_edge("performance", END)
    builder.add_edge("quality", END)

    return builder.compile()

# Global compiled graph instance
review_graph = build_review_graph()
