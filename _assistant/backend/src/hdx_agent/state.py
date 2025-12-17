"""Shared state schemas for all graphs."""

from typing import Annotated, Any
from datetime import datetime
from enum import Enum
from uuid import uuid4
from pydantic import BaseModel, Field
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


class IntentType(str, Enum):
    """Supported intent types for routing."""
    SQL_EXPLAIN = "sql_explain"
    ERROR_EXPLAIN = "error_explain"
    SQL_FIX = "sql_fix"
    SQL_CREATE = "sql_create"
    DATA_RETRIEVE = "data_retrieve"
    FOLLOWUP_ANSWER = "followup"
    UNCLEAR = "unclear"


class ThoughtEntry(BaseModel):
    """Record of a completed subgraph execution."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    intent_type: IntentType
    reasoning: str = Field(description="Why this action was taken")
    action: str = Field(description="What action was performed")
    success: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class FollowupContext(BaseModel):
    """Context for pending user clarification."""
    intent: IntentType
    awaiting: str = Field(description="What information is needed")
    original_request: str
    gathered_info: dict[str, Any] = Field(default_factory=dict)


class IntentDetectionResult(BaseModel):
    """Result from intent detection."""
    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    extracted_sql: str | None = None
    extracted_error: str | None = None


class SubgraphResult(BaseModel):
    """Result from a subgraph execution."""
    success: bool
    output: str
    sql_generated: str | None = None
    query_result: dict[str, Any] | None = None
    error: str | None = None


class EntryGraphState(BaseModel):
    """Main application state for the entry graph."""
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    thoughts: list[ThoughtEntry] = Field(default_factory=list)
    current_intent: IntentType | None = None
    intent_confidence: float = 0.0
    intent_reasoning: str = ""
    pending_followup: FollowupContext | None = None
    subgraph_result: SubgraphResult | None = None
    extracted_sql: str | None = None
    extracted_error: str | None = None
    
    class Config:
        arbitrary_types_allowed = True


class ReActState(BaseModel):
    """State for the ReAct query subgraph."""
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    iteration_count: int = 0
    max_iterations: int = 10
    retry_count: int = 0
    max_retries: int = 3
    final_sql: str | None = None
    query_result: dict[str, Any] | None = None
    
    class Config:
        arbitrary_types_allowed = True


class ExplainState(BaseModel):
    """State for SQL explain subgraph."""
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    sql_to_explain: str = ""
    explanation: str | None = None
    
    class Config:
        arbitrary_types_allowed = True


class ErrorState(BaseModel):
    """State for error explain subgraph."""
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    error_message: str = ""
    sql_context: str | None = None
    explanation: str | None = None
    
    class Config:
        arbitrary_types_allowed = True


class FixState(BaseModel):
    """State for SQL fix subgraph."""
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    broken_sql: str = ""
    error_message: str | None = None
    fixed_sql: str | None = None
    fix_explanation: str | None = None
    
    class Config:
        arbitrary_types_allowed = True
