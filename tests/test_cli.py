"""Tests for agent/cli.py. The LLM and the models endpoint are mocked."""

from __future__ import annotations

import io

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


def test_question_prints_answer_and_cost_line(make_llm) -> None:
    chat = FakeChat(content="Add alt text to images.")
    app, buffer = _app(make_llm, chat)
    assert app.handle("What should I check first?") is True
    out = buffer.getvalue()
    assert "Add alt text to images." in out
    assert "[COST] total $0.000000" in out
    assert "| calls 1" in out
    system, human = chat.calls[0]
    assert human.content == "What should I check first?"
    assert "landing-page" in system.content


def test_model_error_prints_one_error_line(make_llm) -> None:
    app, buffer = _app(make_llm, FakeChat(error=RuntimeError("boom")))
    assert app.handle("hello") is True
    out = buffer.getvalue()
    assert out.startswith("[ERROR] ")
    assert "Traceback" not in out


def test_cost_line_is_per_task(make_llm) -> None:
    app, buffer = _app(make_llm, FakeChat())
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

    assert app.llm.choice.model_id == config["profiles"]["free"]["guard"][0]["id"]
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
