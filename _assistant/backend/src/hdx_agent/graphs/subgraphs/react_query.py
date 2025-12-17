"""ReAct query builder subgraph."""

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from hdx_agent.state import ReActState
from hdx_agent.config import get_llm
from hdx_agent.tools import get_hydrolix_tools
from hdx_agent.prompts import REACT_SYSTEM_PROMPT


async def build_react_subgraph() -> StateGraph:
    """Build the ReAct loop subgraph for query building and execution."""
    graph = StateGraph(ReActState)

    llm = get_llm(streaming=True)
    tools = await get_hydrolix_tools()
    model_with_tools = llm.bind_tools(tools)

    async def reason_node(state: ReActState) -> dict:
        """LLM reasoning step - decide next action."""
        task = ""
        for msg in state.messages:
            if isinstance(msg, HumanMessage):
                task = msg.content

        system_prompt = REACT_SYSTEM_PROMPT.format(task_description=task)

        messages = [SystemMessage(content=system_prompt)] + list(state.messages)
        response = await model_with_tools.ainvoke(messages)

        return {
            "messages": [response],
            "iteration_count": state.iteration_count + 1,
        }

    graph.add_node("reason", reason_node)
    graph.add_node("tools", ToolNode(tools))

    graph.add_edge(START, "reason")
    graph.add_conditional_edges(
        "reason",
        should_continue,
        {
            "tools": "tools",
            "end": END,
        },
    )
    graph.add_edge("tools", "reason")

    return graph


def should_continue(state: ReActState) -> str:
    """Decide whether to call tools or finish the ReAct loop."""
    if state.iteration_count >= state.max_iterations:
        return "end"

    if not state.messages:
        return "end"

    last_message = state.messages[-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    return "end"
