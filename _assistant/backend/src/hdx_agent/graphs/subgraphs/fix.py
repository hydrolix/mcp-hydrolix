"""SQL fix subgraph."""

from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph, START, END

from hdx_agent.state import FixState
from hdx_agent.config import get_llm
from hdx_agent.prompts import SQL_FIX_PROMPT


def build_fix_subgraph() -> StateGraph:
    """Build the SQL fix subgraph."""
    graph = StateGraph(FixState)

    graph.add_node("analyze_and_fix", analyze_and_fix_node)

    graph.add_edge(START, "analyze_and_fix")
    graph.add_edge("analyze_and_fix", END)

    return graph


async def analyze_and_fix_node(state: FixState) -> dict:
    """Analyze the broken SQL and generate a fix."""
    llm = get_llm(streaming=True)

    requirements = ""
    for msg in state.messages[-3:]:
        if isinstance(msg, HumanMessage):
            requirements = msg.content
            break

    prompt = SQL_FIX_PROMPT.format(
        broken_sql=state.broken_sql,
        error_message=state.error_message or "No error message provided",
        requirements=requirements or "Fix the query so it executes correctly",
    )

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    content = response.content
    fixed_sql = None

    if "```sql" in content:
        try:
            fixed_sql = content.split("```sql")[1].split("```")[0].strip()
        except IndexError:
            pass
    elif "```" in content:
        try:
            fixed_sql = content.split("```")[1].split("```")[0].strip()
        except IndexError:
            pass

    return {
        "fixed_sql": fixed_sql,
        "fix_explanation": response.content,
        "messages": [AIMessage(content=response.content)],
    }
