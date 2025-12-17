"""SQL explain subgraph."""

from langchain_core.messages import SystemMessage, AIMessage
from langgraph.graph import StateGraph, START, END

from hdx_agent.state import ExplainState
from hdx_agent.config import get_llm
from hdx_agent.prompts import SQL_EXPLAIN_PROMPT


def build_explain_subgraph() -> StateGraph:
    """Build the SQL explain subgraph."""
    graph = StateGraph(ExplainState)

    graph.add_node("explain_sql", explain_sql_node)

    graph.add_edge(START, "explain_sql")
    graph.add_edge("explain_sql", END)

    return graph


async def explain_sql_node(state: ExplainState) -> dict:
    """Generate an explanation for the SQL query."""
    llm = get_llm(streaming=True)

    context_parts = []
    for msg in state.messages[-5:]:
        if hasattr(msg, 'content'):
            context_parts.append(msg.content[:500])

    prompt = SQL_EXPLAIN_PROMPT.format(
        sql_query=state.sql_to_explain,
        context="\n".join(context_parts) if context_parts else "No additional context",
    )

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    return {
        "explanation": response.content,
        "messages": [AIMessage(content=response.content)],
    }
