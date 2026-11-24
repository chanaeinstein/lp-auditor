"""LangGraph workflow (docs/SPEC.md section 4).

START -> input_guard -> refuse | load_page -> content_guard -> run_checks
-> retrieve_rules -> write_report -> evaluator (-> write_report once) -> confirm_save
-> save_report | END. `confirm_save` stops the graph with `interrupt()`; the caller
resumes it with `resume_task`.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from agent.nodes import (
    AuditState,
    ChatLLM,
    Printer,
    make_confirm_save,
    make_content_guard,
    make_evaluator,
    make_input_guard,
    make_load_page,
    make_refuse,
    make_retrieve_rules,
    make_run_checks,
    make_save_report,
    make_write_report,
    route_after_confirm,
    route_after_eval,
    route_after_guard,
    route_after_load,
)

RUN_NAME = "lp-audit"
DEFAULT_LANGSMITH_PROJECT = "lp-auditor"
INTERRUPT = "__interrupt__"


def build_graph(
    guard_llm: ChatLLM,
    printer: Printer = print,
    writer_llm: ChatLLM | None = None,
    evaluator_llm: ChatLLM | None = None,
) -> Any:
    """Compile the graph. Writer and evaluator default to the guard model (handy in tests)."""
    writer_llm = writer_llm or guard_llm
    evaluator_llm = evaluator_llm or guard_llm
    graph = StateGraph(AuditState)
    graph.add_node("input_guard", make_input_guard(guard_llm, printer))
    graph.add_node("refuse", make_refuse(printer))
    graph.add_node("load_page", make_load_page(printer))
    graph.add_node("content_guard", make_content_guard(guard_llm, printer))
    graph.add_node("run_checks", make_run_checks(printer))
    graph.add_node("retrieve_rules", make_retrieve_rules(printer))
    graph.add_node("write_report", make_write_report(writer_llm, printer))
    graph.add_node("evaluator", make_evaluator(evaluator_llm, printer))
    graph.add_node("confirm_save", make_confirm_save(printer))
    graph.add_node("save_report", make_save_report(printer))

    graph.add_edge(START, "input_guard")
    graph.add_conditional_edges(
        "input_guard", route_after_guard, {"refuse": "refuse", "load_page": "load_page"}
    )
    graph.add_edge("refuse", END)
    graph.add_conditional_edges(
        "load_page", route_after_load, {"end": END, "content_guard": "content_guard"}
    )
    graph.add_edge("content_guard", "run_checks")
    graph.add_edge("run_checks", "retrieve_rules")
    graph.add_edge("retrieve_rules", "write_report")
    graph.add_edge("write_report", "evaluator")
    graph.add_conditional_edges(
        "evaluator",
        route_after_eval,
        {"write_report": "write_report", "confirm_save": "confirm_save"},
    )
    graph.add_conditional_edges(
        "confirm_save", route_after_confirm, {"save_report": "save_report", "end": END}
    )
    graph.add_edge("save_report", END)
    # The checkpointer keeps the state while the graph waits at interrupt().
    return graph.compile(checkpointer=InMemorySaver())


def task_config(thread_id: str) -> dict[str, Any]:
    return {
        "run_name": RUN_NAME,
        "tags": ["lp-auditor"],
        "configurable": {"thread_id": thread_id},
    }


def new_thread_id() -> str:
    return uuid.uuid4().hex


def _updates(graph: Any, graph_input: Any, thread_id: str) -> Iterator[tuple[str, Any]]:
    """Yield (node_name, state_update); an interrupt yields (INTERRUPT, its value)."""
    config = task_config(thread_id)
    for chunk in graph.stream(graph_input, config=config, stream_mode="updates"):
        for node, update in chunk.items():
            if node == INTERRUPT:
                yield INTERRUPT, update[0].value if update else {}
            else:
                yield node, update or {}


def stream_task(
    graph: Any, user_message: str, thread_id: str | None = None
) -> Iterator[tuple[str, Any]]:
    """Run one task. Stops early with an (INTERRUPT, value) item when it needs the user."""
    initial: AuditState = {"user_message": user_message, "revision_count": 0}
    yield from _updates(graph, initial, thread_id or new_thread_id())


def resume_task(graph: Any, answer: Any, thread_id: str) -> Iterator[tuple[str, Any]]:
    """Continue a task that stopped at interrupt(), passing the user's answer."""
    yield from _updates(graph, Command(resume=answer), thread_id)


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
