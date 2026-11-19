"""Tests for agent/llm.py (cost records, budget, error lines). The LLM is mocked."""

from __future__ import annotations

import httpx
import openai
import pytest
from langchain_core.messages import HumanMessage

from agent.llm import (
    BudgetExceededError,
    CostTracker,
    UsageRecord,
    build_chat_model,
    cost_line,
    describe_error,
)
from agent.models import ModelChoice, Price
from tests.conftest import FakeChat


def test_invoke_records_cost_and_theoretical_cost(make_llm) -> None:
    chat = FakeChat(prompt_tokens=100, completion_tokens=20, cost=0.0)
    llm, tracker = make_llm(chat)

    answer = llm.invoke([HumanMessage("hi")], node="guard")

    assert answer == "Use one <h1> per page."
    [record] = tracker.records
    assert record.node == "guard"
    assert record.model == "google/gemma-4-31b-it:free"
    assert (record.prompt_tokens, record.completion_tokens) == (100, 20)
    assert record.cost_usd == 0.0
    assert record.theoretical_cost_usd == pytest.approx(100 * 0.000001 + 20 * 0.000002)


def test_cost_falls_back_to_pricing_when_not_reported(make_llm) -> None:
    paid = ModelChoice(
        "guard",
        "google/gemini-3.1-flash-lite",
        Price(0.00001, 0.00002),
        Price(0.00001, 0.00002),
    )
    llm, tracker = make_llm(
        FakeChat(prompt_tokens=10, completion_tokens=5, cost=None), choice=paid
    )
    llm.invoke([HumanMessage("hi")], node="guard")
    assert tracker.records[0].cost_usd == pytest.approx(10 * 0.00001 + 5 * 0.00002)


def test_reported_cost_is_used(make_llm) -> None:
    paid = ModelChoice("guard", "x/y", Price(1, 1), Price(1, 1))
    llm, tracker = make_llm(
        FakeChat(prompt_tokens=1, completion_tokens=1, cost=0.0042), choice=paid
    )
    llm.invoke([HumanMessage("hi")], node="guard")
    assert tracker.records[0].cost_usd == pytest.approx(0.0042)


def test_budget_stops_call_that_would_exceed_limit(make_llm) -> None:
    chat = FakeChat(cost=0.3)
    llm, tracker = make_llm(chat, tracker=CostTracker(max_cost_usd=0.5))
    tracker.start_task()
    llm.invoke([HumanMessage("first")], node="guard")
    with pytest.raises(BudgetExceededError, match="MAX_COST_USD"):
        llm.invoke([HumanMessage("second")], node="guard")
    assert len(chat.calls) == 1


def test_budget_resets_per_task(make_llm) -> None:
    llm, tracker = make_llm(FakeChat(cost=0.3), tracker=CostTracker(max_cost_usd=0.5))
    tracker.start_task()
    llm.invoke([HumanMessage("a")], node="guard")
    tracker.start_task()
    llm.invoke([HumanMessage("b")], node="guard")
    assert len(tracker.records) == 2
    assert len(tracker.task_records()) == 1


def test_cost_line_format() -> None:
    records = [
        UsageRecord("guard", "m", 100, 20, 0.0, 0.00014),
        UsageRecord("writer", "m", 50, 10, 0.001, 0.001),
    ]
    assert cost_line(records) == (
        "[COST] total $0.001000 (theoretical $0.001140) | tokens in 150 / out 30 | calls 2"
    )


def test_chat_model_points_at_openrouter() -> None:
    chat = build_chat_model("test-key", "google/gemma-4-31b-it:free")
    assert str(chat.openai_api_base).startswith("https://openrouter.ai/api/v1")
    assert chat.extra_body == {"usage": {"include": True}}


def _status_error(
    cls: type[openai.APIStatusError], status: int
) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return cls("err", response=httpx.Response(status, request=request), body=None)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_status_error(openai.AuthenticationError, 401), "(401)"),
        (_status_error(openai.APIStatusError, 402), "(402)"),
        (_status_error(openai.RateLimitError, 429), "(429)"),
        (
            openai.APIConnectionError(request=httpx.Request("POST", "https://x")),
            "network",
        ),
    ],
)
def test_describe_error_lines(exc: BaseException, expected: str) -> None:
    line = describe_error(exc)
    assert expected in line
    assert " - " in line
