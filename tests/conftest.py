"""Shared fakes: no test ever calls a real model or the real network."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage

from agent.llm import CostTracker, OpenRouterLLM
from agent.models import ModelChoice, Price


class FakeChat:
    """Stands in for ChatOpenAI and returns a canned OpenRouter-style response."""

    def __init__(
        self,
        content: str = "Use one <h1> per page.",
        prompt_tokens: int = 100,
        completion_tokens: int = 20,
        cost: float | None = 0.0,
        error: BaseException | None = None,
    ) -> None:
        self.content = content
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cost = cost
        self.error = error
        self.calls: list[list[Any]] = []

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        token_usage: dict[str, Any] = {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }
        if self.cost is not None:
            token_usage["cost"] = self.cost
        return AIMessage(
            content=self.content,
            usage_metadata={
                "input_tokens": self.prompt_tokens,
                "output_tokens": self.completion_tokens,
                "total_tokens": self.prompt_tokens + self.completion_tokens,
            },
            response_metadata={"token_usage": token_usage},
        )


@pytest.fixture(autouse=True)
def no_tracing(monkeypatch) -> None:
    """Tests never send traces to LangSmith."""
    monkeypatch.setenv("LANGSMITH_TRACING", "false")


@pytest.fixture
def free_choice() -> ModelChoice:
    return ModelChoice(
        role="guard",
        model_id="google/gemma-4-31b-it:free",
        price=Price(0.0, 0.0),
        theoretical_price=Price(0.000001, 0.000002),
    )


@pytest.fixture
def make_llm(free_choice: ModelChoice):
    def _make(
        chat: FakeChat,
        tracker: CostTracker | None = None,
        choice: ModelChoice | None = None,
    ):
        tracker = tracker or CostTracker()
        llm = OpenRouterLLM(
            "test-key", choice or free_choice, tracker, chat_factory=lambda k, m: chat
        )
        return llm, tracker

    return _make
