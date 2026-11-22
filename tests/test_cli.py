"""Tests for agent/cli.py. The LLM and the models endpoint are mocked."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

from agent import cli
from agent.llm import CostTracker
from agent.models import ModelsUnavailableError, Price
from tests.conftest import FakeChat


def _console() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    return Console(file=buffer, force_terminal=False, width=200), buffer


def _app(make_llm, chat: FakeChat) -> tuple[cli.App, io.StringIO]:
    console, buffer = _console()
    llm, tracker = make_llm(chat)
    return cli.App(console, llm, tracker), buffer


@pytest.mark.parametrize("command", ["help", "?", "  HELP  "])
def test_help_prints_guide(make_llm, command: str) -> None:
    chat = FakeChat()
    app, buffer = _app(make_llm, chat)
    assert app.handle(command) is True
    assert "/quit" in buffer.getvalue()
    assert "audit" in buffer.getvalue()
    assert chat.calls == []


def test_quit_ends_session(make_llm) -> None:
    app, buffer = _app(make_llm, FakeChat())
    assert app.handle("/quit") is False
    assert "Goodbye" in buffer.getvalue()


def test_empty_line_is_ignored(make_llm) -> None:
    chat = FakeChat()
    app, _ = _app(make_llm, chat)
    assert app.handle("   ") is True
    assert chat.calls == []


SEO_PAGE = (
    Path(__file__).resolve().parent.parent / "evals" / "fixtures" / "page_seo.html"
)
IN_SCOPE = '{"in_scope": true, "injection": false, "reason": "audit"}'
OUT_OF_SCOPE = '{"in_scope": false, "injection": false, "reason": "weather"}'


def test_message_runs_graph_and_prints_report_and_cost_line(make_llm) -> None:
    console, buffer = _console()
    guard, tracker = make_llm(FakeChat(content=IN_SCOPE))
    writer_chat = FakeChat(
        content="## Summary\nNo title.\n\n## Issues\n### [high] SEO-01"
    )
    writer, _ = make_llm(writer_chat, tracker)
    app = cli.App(console, guard, tracker, writer)
    assert app.handle(f"audit {SEO_PAGE}") is True
    out = buffer.getvalue()
    for node in (
        "input_guard",
        "load_page",
        "run_checks",
        "retrieve_rules",
        "write_report",
    ):
        assert f"[INFO] Entering Node: {node}" in out
    assert "# Landing Page Audit: page_seo.html" in out
    assert "Score: 18/24 | Issues: 6 (high 1, medium 3, low 2)" in out
    assert "### [high] SEO-01" in out
    assert "[COST] total $0.000000" in out
    assert "| calls 2" in out
    assert len(writer_chat.calls) == 1


def test_missing_file_prints_one_error_line(make_llm) -> None:
    app, buffer = _app(make_llm, FakeChat(content=IN_SCOPE))
    app.handle("audit no_such_page.html")
    out = buffer.getvalue()
    assert "[ERROR] File not found:" in out
    assert "check the path and try again" in out
    assert "run_checks" not in out


def test_out_of_scope_message_is_refused(make_llm) -> None:
    app, buffer = _app(make_llm, FakeChat(content=OUT_OF_SCOPE))
    app.handle("What's the weather?")
    out = buffer.getvalue()
    assert "[INFO] Entering Node: refuse" in out
    assert "I can only audit landing-page HTML files" in out


def test_model_error_prints_one_error_line(make_llm) -> None:
    app, buffer = _app(make_llm, FakeChat(error=RuntimeError("boom")))
    assert app.handle("hello") is True
    out = buffer.getvalue()
    assert "[ERROR] " in out
    assert "Traceback" not in out


def test_invalid_guard_json_prints_one_error_line(make_llm) -> None:
    app, buffer = _app(make_llm, FakeChat(content="not json"))
    app.handle("audit page.html")
    out = buffer.getvalue()
    assert "[ERROR] The input_guard model returned invalid JSON twice" in out
    assert "| calls 2" in out


def test_cost_line_is_per_task(make_llm) -> None:
    app, buffer = _app(make_llm, FakeChat(content=IN_SCOPE))
    app.handle("one")
    app.handle("two")
    assert buffer.getvalue().count("| calls 1") == 2


def test_run_repl_stops_on_quit_and_eof(make_llm) -> None:
    app, buffer = _app(make_llm, FakeChat())
    lines = iter(["help", "/quit", "never read"])
    cli.run_repl(app, lambda: next(lines))
    assert next(lines) == "never read"

    def eof() -> str:
        raise EOFError

    cli.run_repl(app, eof)
    assert buffer.getvalue().count("Goodbye") == 2


def test_get_api_key_prompts_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert cli.get_api_key(prompt=lambda _: " typed-key ") == "typed-key"


def test_read_max_cost(monkeypatch) -> None:
    monkeypatch.delenv("MAX_COST_USD", raising=False)
    assert cli.read_max_cost() == 0.50
    monkeypatch.setenv("MAX_COST_USD", "0.2")
    assert cli.read_max_cost() == 0.2
    monkeypatch.setenv("MAX_COST_USD", "abc")
    with pytest.raises(ValueError, match="MAX_COST_USD"):
        cli.read_max_cost()


def test_build_app_selects_guard_model(monkeypatch) -> None:
    config = cli.load_config()
    ids = {
        e["id"]
        for roles in config["profiles"].values()
        for es in roles.values()
        for e in es
    }
    monkeypatch.setattr(cli, "load_env", lambda: None)
    monkeypatch.setattr(
        cli, "fetch_available_models", lambda base_url: {i: Price() for i in ids}
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PROFILE", "free")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    console, buffer = _console()

    app = cli.build_app(console)

    free = config["profiles"]["free"]
    assert app.llm.choice.model_id == free["guard"][0]["id"]
    assert app.writer_llm.choice.model_id == free["writer"][0]["id"]
    assert app.writer_llm.tracker is app.tracker
    assert isinstance(app.tracker, CostTracker)
    assert "[INFO] LangSmith tracing is off" in buffer.getvalue()


def test_build_app_exits_cleanly_when_no_model(monkeypatch) -> None:
    def offline(base_url: str) -> dict:
        raise ModelsUnavailableError(
            "Cannot read the OpenRouter model list - check your network connection"
        )

    monkeypatch.setattr(cli, "load_env", lambda: None)
    monkeypatch.setattr(cli, "fetch_available_models", offline)
    console, buffer = _console()
    with pytest.raises(SystemExit):
        cli.build_app(console)
    assert buffer.getvalue().startswith("[ERROR] Cannot read the OpenRouter model list")


def test_byte_order_mark_is_ignored(make_llm) -> None:
    app, buffer = _app(make_llm, FakeChat())
    assert app.handle("﻿help") is True
    assert "/quit" in buffer.getvalue()
