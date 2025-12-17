"""Subgraph definitions."""

from hdx_agent.graphs.subgraphs.explain import build_explain_subgraph
from hdx_agent.graphs.subgraphs.error import build_error_subgraph
from hdx_agent.graphs.subgraphs.fix import build_fix_subgraph
from hdx_agent.graphs.subgraphs.react_query import build_react_subgraph

__all__ = [
    "build_explain_subgraph",
    "build_error_subgraph",
    "build_fix_subgraph",
    "build_react_subgraph",
]
