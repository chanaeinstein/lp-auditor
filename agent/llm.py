"""OpenRouter chat client with per-call cost records and the MAX_COST_USD budget."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import openai
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from agent.models import DEFAULT_BASE_URL, ModelChoice

DEFAULT_MAX_COST_USD = 0.50
APP_TITLE = "LP Auditor Agent"


class BudgetExceededError(Exception):
    """The next LLM call would exceed MAX_COST_USD for the current task."""


@dataclass(frozen=True)
class UsageRecord:
    node: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    theoretical_cost_usd: float


@dataclass
class CostTracker:
    """Keeps every call record of the session and enforces the per-task budget."""

    max_cost_usd: float = DEFAULT_MAX_COST_USD
    records: list[UsageRecord] = field(default_factory=list)
    _task_start: int = 0

    def start_task(self) -> None:
        self._task_start = len(self.records)

    def task_records(self) -> list[UsageRecord]:
        return self.records[self._task_start :]

    def add(self, record: UsageRecord) -> None:
        self.records.append(record)

    def check_budget(self) -> None:
        """Stop before a call that would push the task over MAX_COST_USD.

        The next call is estimated at the cost of the most expensive call so far in the task.
        """
        task = self.task_records()
        spent = sum(r.cost_usd for r in task)
        estimate = max((r.cost_usd for r in task), default=0.0)
        if spent + estimate > self.max_cost_usd:
            raise BudgetExceededError(
                f"Cost limit reached (${spent:.4f} of ${self.max_cost_usd:.2f}) "
                "- raise MAX_COST_USD in .env or start a smaller task"
            )


def cost_line(records: Sequence[UsageRecord]) -> str:
    total = sum(r.cost_usd for r in records)
    theoretical = sum(r.theoretical_cost_usd for r in records)
    tokens_in = sum(r.prompt_tokens for r in records)
    tokens_out = sum(r.completion_tokens for r in records)
    return (
        f"[COST] total ${total:.6f} (theoretical ${theoretical:.6f}) "
        f"| tokens in {tokens_in} / out {tokens_out} | calls {len(records)}"
    )


def build_chat_model(
    api_key: str, model_id: str, base_url: str = DEFAULT_BASE_URL
) -> ChatOpenAI:
    """A ChatOpenAI client pointed at OpenRouter, with usage accounting turned on."""
    return ChatOpenAI(
        model=model_id,
        api_key=api_key,
        base_url=base_url,
        timeout=60,
        max_retries=0,
        extra_body={"usage": {"include": True}},
        default_headers={"X-Title": APP_TITLE},
    )


ChatFactory = Callable[[str, str], Any]


class OpenRouterLLM:
    """Runs chat calls for one role and records the cost of each call."""

    def __init__(
        self,
        api_key: str,
        choice: ModelChoice,
        tracker: CostTracker,
        chat_factory: ChatFactory | None = None,
    ) -> None:
        self.choice = choice
        self.tracker = tracker
        factory = chat_factory or build_chat_model
        self._chat = factory(api_key, choice.model_id)

    def invoke(self, messages: Sequence[BaseMessage], node: str) -> str:
        self.tracker.check_budget()
        response = self._chat.invoke(list(messages))
        self.tracker.add(self._record(response, node))
        content = response.content
        return content if isinstance(content, str) else str(content)

    def _record(self, response: Any, node: str) -> UsageRecord:
        usage = getattr(response, "usage_metadata", None) or {}
        raw = (getattr(response, "response_metadata", None) or {}).get(
            "token_usage"
        ) or {}
        prompt_tokens = int(usage.get("input_tokens") or raw.get("prompt_tokens") or 0)
        completion_tokens = int(
            usage.get("output_tokens") or raw.get("completion_tokens") or 0
        )
        reported = raw.get("cost")
        cost = (
            float(reported)
            if reported is not None
            else self.choice.price.cost(prompt_tokens, completion_tokens)
        )
        theoretical = self.choice.theoretical_price.cost(
            prompt_tokens, completion_tokens
        )
        return UsageRecord(
            node=node,
            model=self.choice.model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            theoretical_cost_usd=max(theoretical, cost),
        )


def describe_error(exc: BaseException) -> str:
    """One-line '<what happened> - <what to do>' text for a failed LLM call."""
    if isinstance(exc, BudgetExceededError):
        return str(exc)
    if isinstance(exc, openai.AuthenticationError):
        return (
            "OpenRouter rejected the API key (401) - check OPENROUTER_API_KEY in .env"
        )
    if isinstance(exc, openai.RateLimitError):
        return "Rate limit reached (429) - wait a minute and try again"
    if isinstance(exc, openai.APIStatusError) and exc.status_code == 402:
        return "Not enough OpenRouter credit (402) - add credit or use PROFILE=free"
    if isinstance(exc, openai.APIConnectionError):
        return "Cannot reach OpenRouter - check your network connection"
    if isinstance(exc, openai.APIStatusError):
        return f"OpenRouter returned HTTP {exc.status_code} - try again later"
    return f"Model call failed ({type(exc).__name__}) - try again"
