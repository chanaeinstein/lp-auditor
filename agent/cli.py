"""CLI entrypoint: `python -m agent.cli` or `agent.exe`."""

from __future__ import annotations

import getpass
import os
import sys
from collections.abc import Callable
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

from agent.graph import build_graph, configure_tracing, stream_task
from agent.llm import (
    DEFAULT_MAX_COST_USD,
    CostTracker,
    OpenRouterLLM,
    cost_line,
    describe_error,
)
from agent.models import (
    DEFAULT_BASE_URL,
    ModelConfigError,
    ModelsUnavailableError,
    fetch_available_models,
    load_config,
    select_models,
)
from agent.nodes import StructuredOutputError

PROMPT = "lp-auditor> "

HELP_TEXT = """\
LP Auditor Agent - audits a local landing-page HTML file for SEO, accessibility,
basic performance, i18n and link-safety issues, and writes a fix report.

Commands:
  help, ?        Show this guide
  /quit          Exit
  audit <path>   Audit a landing-page HTML file (or any message with a path)

Example:
  audit C:\\pages\\black-friday.html
"""


def _out(console: Console, text: str, style: str | None = None) -> None:
    """Print text literally: brackets like [COST] must not be read as rich markup."""
    console.print(text, style=style, markup=False, highlight=False, soft_wrap=True)


def error_line(console: Console, message: str) -> None:
    _out(console, f"[ERROR] {message}", style="red")


def load_env() -> None:
    """Load .env next to the exe, or from the working directory / project root."""
    if getattr(sys, "frozen", False):
        candidates = [Path(sys.executable).resolve().parent / ".env"]
    else:
        candidates = [
            Path.cwd() / ".env",
            Path(__file__).resolve().parent.parent / ".env",
        ]
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=False)
            return


def get_api_key(prompt: Callable[[str], str] = getpass.getpass) -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        key = prompt("OpenRouter API key (input hidden): ").strip()
    return key


def read_max_cost() -> float:
    raw = os.environ.get("MAX_COST_USD", "").strip()
    if not raw:
        return DEFAULT_MAX_COST_USD
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"MAX_COST_USD is not a number: {raw!r} - fix it in .env"
        ) from exc
    if value <= 0:
        raise ValueError("MAX_COST_USD must be greater than 0 - fix it in .env")
    return value


class App:
    """The REPL logic, independent of the input source so it can be tested."""

    def __init__(
        self,
        console: Console,
        llm: OpenRouterLLM,
        tracker: CostTracker,
        writer_llm: OpenRouterLLM | None = None,
    ) -> None:
        self.console = console
        self.llm = llm
        self.writer_llm = writer_llm or llm
        self.tracker = tracker
        self.graph = build_graph(
            llm,
            printer=lambda text: _out(console, text),
            writer_llm=self.writer_llm,
        )

    def handle(self, line: str) -> bool:
        """Handle one input line. Returns False when the session should end."""
        text = line.replace("﻿", "").strip()
        if not text:
            return True
        command = text.lower()
        if command in ("help", "?"):
            _out(self.console, HELP_TEXT)
            return True
        if command == "/quit":
            _out(self.console, "Goodbye.")
            return False
        self.ask(text)
        return True

    def ask(self, message: str) -> None:
        """Run one task through the graph, streaming node updates."""
        self.tracker.start_task()
        reply = ""
        error = ""
        try:
            for _node, update in stream_task(self.graph, message):
                reply = update.get("reply", reply)
                error = update.get("error", error)
        except StructuredOutputError as exc:
            error_line(self.console, str(exc))
        except Exception as exc:  # noqa: BLE001 - every failure becomes one clear line
            error_line(self.console, describe_error(exc))
        else:
            if error:
                error_line(self.console, error)
            elif reply:
                _out(self.console, reply.strip())
        _out(self.console, cost_line(self.tracker.task_records()), style="cyan")


def run_repl(app: App, read_line: Callable[[], str]) -> None:
    while True:
        try:
            line = read_line()
        except (EOFError, KeyboardInterrupt):
            _out(app.console, "Goodbye.")
            return
        if not app.handle(line):
            return


def build_app(console: Console) -> App:
    """Startup: env, key, model availability check. Raises SystemExit(1) on a clear error."""
    load_env()
    profile = os.environ.get("PROFILE", "").strip() or "free"
    try:
        max_cost = read_max_cost()
        config = load_config()
        base_url = config.get("base_url", DEFAULT_BASE_URL)
        available = fetch_available_models(base_url)
        choices = select_models(config, profile, available)
    except (ValueError, ModelConfigError, ModelsUnavailableError) as exc:
        error_line(console, str(exc))
        raise SystemExit(1) from exc

    if configure_tracing():
        _out(
            console,
            f"[INFO] LangSmith tracing is on (project: {os.environ['LANGSMITH_PROJECT']})",
        )
    else:
        _out(console, "[INFO] LangSmith tracing is off")

    api_key = get_api_key()
    if not api_key:
        error_line(console, "No OpenRouter API key - add OPENROUTER_API_KEY to .env")
        raise SystemExit(1)

    tracker = CostTracker(max_cost_usd=max_cost)
    guard, writer = choices["guard"], choices["writer"]
    llm = OpenRouterLLM(api_key, guard, tracker)
    writer_llm = OpenRouterLLM(api_key, writer, tracker)
    _out(
        console,
        f"[INFO] Profile: {profile} | guard model: {guard.model_id} "
        f"| writer model: {writer.model_id}",
    )
    return App(console, llm, tracker, writer_llm)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if not sys.stdin.isatty() and hasattr(sys.stdin, "reconfigure"):
        # Piped input (evals, PowerShell) is UTF-8 and may start with a BOM.
        sys.stdin.reconfigure(encoding="utf-8-sig", errors="replace")
    console = Console()
    _out(
        console,
        "LP Auditor Agent - type 'help' for commands, '/quit' to exit.",
        style="bold",
    )
    try:
        app = build_app(console)
    except SystemExit as exc:
        return int(exc.code or 1)

    try:
        run_repl(app, make_line_reader())
    finally:
        flush_tracing()
    return 0


def flush_tracing() -> None:
    """Send pending LangSmith traces before exit, so no thread dies at shutdown."""
    from langchain_core.tracers.langchain import wait_for_all_tracers

    wait_for_all_tracers()


def make_line_reader() -> Callable[[], str]:
    """prompt_toolkit in a real terminal; plain input() when stdin is piped."""
    if not sys.stdin.isatty():
        return lambda: input()

    from prompt_toolkit import PromptSession

    session: PromptSession[str] = PromptSession()
    return lambda: session.prompt(PROMPT)


if __name__ == "__main__":
    sys.exit(main())
