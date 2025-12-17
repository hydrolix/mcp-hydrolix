"""Entry graph with intent routing."""

import json
from uuid import uuid4
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, START, END

from hdx_agent.state import (
    EntryGraphState,
    IntentType,
    ThoughtEntry,
    FollowupContext,
    SubgraphResult,
    ExplainState,
    ErrorState,
    FixState,
    ReActState,
)
from hdx_agent.config import get_llm
from hdx_agent.prompts import INTENT_DETECTION_PROMPT
from hdx_agent.graphs.subgraphs.explain import build_explain_subgraph
from hdx_agent.graphs.subgraphs.error import build_error_subgraph
from hdx_agent.graphs.subgraphs.fix import build_fix_subgraph
from hdx_agent.graphs.subgraphs.react_query import build_react_subgraph


def build_entry_graph() -> StateGraph:
    """Build the entry graph that routes to specialized subgraphs."""
    graph = StateGraph(EntryGraphState)

    graph.add_node("detect_intent", detect_intent_node)
    graph.add_node("dispatch_explain", dispatch_explain_node)
    graph.add_node("dispatch_error", dispatch_error_node)
    graph.add_node("dispatch_fix", dispatch_fix_node)
    graph.add_node("dispatch_react_query", dispatch_react_query_node)
    graph.add_node("request_clarification", request_clarification_node)
    graph.add_node("record_thought", record_thought_node)

    graph.add_edge(START, "detect_intent")

    graph.add_conditional_edges(
        "detect_intent",
        route_by_intent,
        {
            "explain": "dispatch_explain",
            "error": "dispatch_error",
            "fix": "dispatch_fix",
            "query": "dispatch_react_query",
            "clarify": "request_clarification",
        },
    )

    for node in ["dispatch_explain", "dispatch_error", "dispatch_fix", "dispatch_react_query"]:
        graph.add_edge(node, "record_thought")

    graph.add_edge("record_thought", END)
    graph.add_edge("request_clarification", END)

    return graph


async def detect_intent_node(state: EntryGraphState) -> dict:
    """Detect the user's intent from their message."""
    llm = get_llm(streaming=False)

    last_message = None
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            last_message = msg.content
            break

    if not last_message:
        return {
            "current_intent": IntentType.UNCLEAR,
            "intent_confidence": 0.0,
            "intent_reasoning": "No user message found",
        }

    context_messages = []
    for msg in state.messages[-6:-1]:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        content = msg.content if hasattr(msg, "content") else str(msg)
        context_messages.append(f"{role}: {content[:200]}...")

    conversation_context = "\n".join(context_messages) if context_messages else "None"

    prompt = INTENT_DETECTION_PROMPT.format(
        user_message=last_message,
        conversation_context=conversation_context,
    )

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    try:
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        result = json.loads(content.strip())

        return {
            "current_intent": IntentType(result["intent"]),
            "intent_confidence": float(result.get("confidence", 0.8)),
            "intent_reasoning": result.get("reasoning", ""),
            "extracted_sql": result.get("extracted_sql"),
            "extracted_error": result.get("extracted_error"),
        }
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        return {
            "current_intent": IntentType.UNCLEAR,
            "intent_confidence": 0.0,
            "intent_reasoning": f"Failed to parse intent: {e}",
        }


def route_by_intent(state: EntryGraphState) -> str:
    """Route to appropriate handler based on detected intent."""
    intent = state.current_intent

    if intent == IntentType.SQL_EXPLAIN:
        return "explain"
    elif intent == IntentType.ERROR_EXPLAIN:
        return "error"
    elif intent == IntentType.SQL_FIX:
        return "fix"
    elif intent in [IntentType.SQL_CREATE, IntentType.DATA_RETRIEVE, IntentType.FOLLOWUP_ANSWER]:
        return "query"
    else:
        return "clarify"


async def dispatch_explain_node(state: EntryGraphState) -> dict:
    """Dispatch to the SQL explain subgraph."""
    subgraph = build_explain_subgraph().compile()

    initial_state = ExplainState(
        messages=state.messages,
        sql_to_explain=state.extracted_sql or "",
    )

    result = await subgraph.ainvoke(initial_state)

    return {
        "subgraph_result": SubgraphResult(
            success=True,
            output=result.get("explanation", ""),
        ),
        "messages": [AIMessage(content=result.get("explanation", "Unable to explain the SQL."))],
    }


async def dispatch_error_node(state: EntryGraphState) -> dict:
    """Dispatch to the error explain subgraph."""
    subgraph = build_error_subgraph().compile()

    initial_state = ErrorState(
        messages=state.messages,
        error_message=state.extracted_error or "",
        sql_context=state.extracted_sql,
    )

    result = await subgraph.ainvoke(initial_state)

    return {
        "subgraph_result": SubgraphResult(
            success=True,
            output=result.get("explanation", ""),
        ),
        "messages": [AIMessage(content=result.get("explanation", "Unable to explain the error."))],
    }


async def dispatch_fix_node(state: EntryGraphState) -> dict:
    """Dispatch to the SQL fix subgraph."""
    subgraph = build_fix_subgraph().compile()

    initial_state = FixState(
        messages=state.messages,
        broken_sql=state.extracted_sql or "",
        error_message=state.extracted_error,
    )

    result = await subgraph.ainvoke(initial_state)

    output_parts = []
    if result.get("fix_explanation"):
        output_parts.append(result["fix_explanation"])
    if result.get("fixed_sql"):
        output_parts.append(f"\n\n```sql\n{result['fixed_sql']}\n```")

    return {
        "subgraph_result": SubgraphResult(
            success=True,
            output="\n".join(output_parts),
            sql_generated=result.get("fixed_sql"),
        ),
        "messages": [AIMessage(content="\n".join(output_parts) or "Unable to fix the SQL.")],
    }


async def dispatch_react_query_node(state: EntryGraphState) -> dict:
    """Dispatch to the ReAct query builder subgraph."""
    subgraph = (await build_react_subgraph()).compile()

    initial_state = ReActState(
        messages=state.messages,
        max_iterations=10,
        max_retries=3,
    )

    result = await subgraph.ainvoke(initial_state)

    final_message = ""
    for msg in reversed(result.get("messages", [])):
        if isinstance(msg, AIMessage) and msg.content:
            final_message = msg.content
            break

    return {
        "subgraph_result": SubgraphResult(
            success=True,
            output=final_message,
            sql_generated=result.get("final_sql"),
            query_result=result.get("query_result"),
        ),
        "messages": result.get("messages", [])[-1:],
    }


async def request_clarification_node(state: EntryGraphState) -> dict:
    """Ask the user for clarification."""
    llm = get_llm(streaming=True)

    last_content = ""
    if state.messages:
        last_msg = state.messages[-1]
        last_content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    response = await llm.ainvoke(
        [
            SystemMessage(
                content="You are a helpful assistant. Ask a clarifying question to understand what the user needs help with regarding their ClickHouse database."
            ),
            HumanMessage(content=f"The user said: {last_content}"),
        ]
    )

    return {
        "messages": [AIMessage(content=response.content)],
        "pending_followup": FollowupContext(
            intent=IntentType.UNCLEAR,
            awaiting="clarification",
            original_request=last_content,
        ),
    }


async def record_thought_node(state: EntryGraphState) -> dict:
    """Record the completed action as a thought."""
    thought = ThoughtEntry(
        id=str(uuid4()),
        intent_type=state.current_intent or IntentType.UNCLEAR,
        reasoning=state.intent_reasoning,
        action=f"Processed {state.current_intent.value if state.current_intent else 'unknown'} request",
        success=state.subgraph_result.success if state.subgraph_result else False,
        metadata={
            "confidence": state.intent_confidence,
            "sql_generated": state.subgraph_result.sql_generated if state.subgraph_result else None,
        },
    )

    return {
        "thoughts": [thought],
    }
