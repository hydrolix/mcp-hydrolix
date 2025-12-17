"""Extended LangGraphAgent with custom event emission."""

from typing import Any
from ag_ui.core import CustomEvent, EventType
from ag_ui_langgraph import LangGraphAgent


class HydrolixAgent(LangGraphAgent):
    """
    Extended LangGraphAgent with custom event emission for ClickHouse-specific features.

    The base class handles standard AG-UI events:
    - RUN_STARTED / RUN_FINISHED
    - TEXT_MESSAGE_* streaming
    - TOOL_CALL_* events
    - STATE_SNAPSHOT / STATE_DELTA
    - STEP_STARTED / STEP_FINISHED

    This class adds:
    - Custom "thought_added" events for the Thoughts Panel
    - Custom "intent_detected" events for routing visibility
    """

    def __init__(self, name: str, description: str, graph: Any):
        super().__init__(name=name, description=description, graph=graph)
        self._seen_thoughts: set[str] = set()

    async def on_state_update(self, state: dict, node_name: str):
        """
        Hook called after each node execution.
        Override to emit custom events based on state changes.
        """
        if hasattr(super(), 'on_state_update'):
            await super().on_state_update(state, node_name)

        if "thoughts" in state and state["thoughts"]:
            latest_thought = state["thoughts"][-1]
            if self._is_new_thought(latest_thought):
                await self.emit_custom_event(
                    name="thought_added",
                    data=self._serialize_thought(latest_thought),
                )

        if node_name == "detect_intent" and "current_intent" in state:
            await self.emit_custom_event(
                name="intent_detected",
                data={
                    "intent": state["current_intent"],
                    "confidence": state.get("intent_confidence", 1.0),
                    "reasoning": state.get("intent_reasoning", ""),
                },
            )

    async def emit_custom_event(self, name: str, data: Any):
        """Emit a custom AG-UI event."""
        event = CustomEvent(
            type=EventType.CUSTOM,
            name=name,
            value=data,
        )
        await self._emit(event)

    def _is_new_thought(self, thought: Any) -> bool:
        """Check if thought was just added."""
        thought_id = thought.id if hasattr(thought, 'id') else thought.get("id")
        if thought_id in self._seen_thoughts:
            return False
        self._seen_thoughts.add(thought_id)
        return True

    def _serialize_thought(self, thought: Any) -> dict:
        """Serialize a thought entry for transmission."""
        if hasattr(thought, 'model_dump'):
            return thought.model_dump()
        elif hasattr(thought, 'dict'):
            return thought.dict()
        return dict(thought)
