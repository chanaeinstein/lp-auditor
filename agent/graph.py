"""LangGraph workflow.

Day 3: START -> input_guard -> (refuse | load_page -> run_checks) -> END.
Days 4-5 add the rest of the audit path from docs/SPEC.md section 4.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    AuditState,
    ChatLLM,
    Printer,
    make_input_guard,
    make_load_page,
    make_refuse,
    make_run_checks,
    route_after_guard,
    route_after_load,
)

RUN_NAME = "lp-audit"
DEFAULT_LANGSMITH_PROJECT = "lp-auditor"


def build_graph(guard_llm: ChatLLM, printer: Printer = print) -> Any:
    graph = StateGraph(AuditState)
    graph.add_node("input_guard", make_input_guard(guard_llm, printer))
    graph.add_node("refuse", make_refuse(printer))
    graph.add_node("load_page", make_load_page(printer))
    graph.add_node("run_checks", make_run_checks(printer))
    graph.add_edge(START, "input_guard")
    graph.add_conditional_edges(
        "input_guard", route_after_guard, {"refuse": "refuse", "load_page": "load_page"}
    )
    graph.add_conditional_edges(
        "load_page", route_after_load, {"end": END, "run_checks": "run_checks"}
    )
    graph.add_edge("refuse", END)
    graph.add_edge("run_checks", END)
    return graph.compile()


def stream_task(graph: Any, user_message: str) -> Iterator[tuple[str, AuditState]]:
    """Run one task and yield (node_name, state_update) as each node finishes."""
    config = {"run_name": RUN_NAME, "tags": ["lp-auditor"]}
    initial: AuditState = {"user_message": user_message, "revision_count": 0}
    for chunk in graph.stream(initial, config=config, stream_mode="updates"):
        for node, update in chunk.items():
            yield node, update or {}


def configure_tracing() -> bool:
    """Turn LangSmith tracing on when a key exists. Returns True when tracing is on."""
    if not os.environ.get("LANGSMITH_API_KEY", "").strip():
        os.environ["LANGSMITH_TRACING"] = "false"
        return False
    if os.environ.get("LANGSMITH_TRACING", "").strip().lower() in ("", "1", "yes"):
        os.environ["LANGSMITH_TRACING"] = "true"
    if not os.environ.get("LANGSMITH_PROJECT", "").strip():
        os.environ["LANGSMITH_PROJECT"] = DEFAULT_LANGSMITH_PROJECT
    return os.environ["LANGSMITH_TRACING"].strip().lower() == "true"
