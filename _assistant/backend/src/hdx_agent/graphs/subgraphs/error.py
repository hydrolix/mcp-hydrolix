"""Error explain subgraph."""

from langchain_core.messages import SystemMessage, AIMessage
from langgraph.graph import StateGraph, START, END

from hdx_agent.state import ErrorState
from hdx_agent.config import get_llm
from hdx_agent.prompts import ERROR_EXPLAIN_PROMPT


def build_error_subgraph() -> StateGraph:
    """Build the error explain subgraph."""
    graph = StateGraph(ErrorState)

    graph.add_node("explain_error", explain_error_node)

    graph.add_edge(START, "explain_error")
    graph.add_edge("explain_error", END)

    return graph


async def explain_error_node(state: ErrorState) -> dict:
    """Generate an explanation for the error message."""
    llm = get_llm(streaming=True)

    context_parts = []
    for msg in state.messages[-5:]:
        if hasattr(msg, 'content'):
            context_parts.append(msg.content[:500])

    prompt = ERROR_EXPLAIN_PROMPT.format(
        error_message=state.error_message,
        sql_context=state.sql_context or "No SQL provided",
        context="\n".join(context_parts) if context_parts else "No additional context",
    )

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    return {
        "explanation": response.content,
        "messages": [AIMessage(content=response.content)],
    }
