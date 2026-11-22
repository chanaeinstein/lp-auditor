"""Tests for the write_report node in agent/nodes.py. The LLM is mocked."""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.nodes import (
    WRITE_REPORT_PROMPT,
    make_write_report,
    report_body,
    report_header,
    sort_findings,
)
from agent.tools import load_page, retrieve_rules, run_checks
from tests.conftest import FakeChat

FIXTURES = Path(__file__).resolve().parent.parent / "evals" / "fixtures"
BODY = "## Summary\nTwo problems.\n\n## Issues\n### [high] SEO-01 - Missing page title"


def _f(rule_id: str, severity: str) -> dict:
    return {"rule_id": rule_id, "severity": severity, "element": "<x>", "detail": "d"}


def _state(page: str) -> dict:
    path, html = load_page(str(FIXTURES / page))
    findings = run_checks(html)
    message = f"audit {path}"
    return {
        "user_message": message,
        "page_path": str(path),
        "findings": findings,
        "rules": retrieve_rules(findings, message),
    }


def _write(make_llm, state: dict, reply: str = BODY):
    chat = FakeChat(content=reply)
    llm, tracker = make_llm(chat)
    lines: list[str] = []
    update = make_write_report(llm, lines.append)(state)
    return update, chat, tracker, lines


def test_sort_findings_high_to_low_and_stable() -> None:
    findings = [_f("A", "low"), _f("B", "high"), _f("C", "medium"), _f("D", "high")]
    assert [f["rule_id"] for f in sort_findings(findings)] == ["B", "D", "C", "A"]


def test_report_header_counts_and_score() -> None:
    findings = [_f("SEO-01", "high"), _f("A11Y-02", "high"), _f("A11Y-02", "high")]
    findings.append(_f("SEO-02", "low"))
    header = report_header(r"C:\pages\promo.html", findings)
    assert header == (
        "# Landing Page Audit: promo.html\n"
        "Score: 21/24 | Issues: 4 (high 3, medium 0, low 1)"
    )


def test_report_header_ignores_sec_inj_in_score() -> None:
    header = report_header("p.html", [_f("SEC-INJ", "high")])
    assert "Score: 24/24 | Issues: 1 (high 1, medium 0, low 0)" in header


def test_report_body_drops_fences_and_model_title() -> None:
    reply = "```markdown\n# My title\nScore: 99/99\n\n" + BODY + "\n```"
    assert report_body(reply) == BODY
    assert report_body("plain text") == "plain text"


def test_write_report_builds_full_report(make_llm) -> None:
    state = _state("page_seo.html")
    update, chat, tracker, lines = _write(make_llm, state)
    assert lines == ["[INFO] Entering Node: write_report"]
    report = update["report"]
    assert report.startswith(
        "# Landing Page Audit: page_seo.html\n"
        "Score: 18/24 | Issues: 6 (high 1, medium 3, low 2)\n\n## Summary"
    )
    assert update["reply"] == report
    assert [r.node for r in tracker.records] == ["write_report"]

    system, user = chat.calls[0]
    assert isinstance(system, SystemMessage)
    assert system.content == WRITE_REPORT_PROMPT
    assert isinstance(user, HumanMessage)
    sent = json.loads(
        user.content.split("high to low:\n", 1)[1].split("\n\nRule base")[0]
    )
    assert [f["rule_id"] for f in sent] == [
        f["rule_id"] for f in sort_findings(state["findings"])
    ]
    assert sent[0]["severity"] == "high"
    for chunk in state["rules"]:
        assert chunk in user.content


def test_writer_prompt_states_the_principles() -> None:
    for phrase in (
        "## Summary",
        "## Issues",
        "## Security notes",
        "never issues",
        "data",
    ):
        assert phrase in WRITE_REPORT_PROMPT


def test_clean_page_sends_no_findings(make_llm) -> None:
    state = _state("page_clean.html")
    reply = "## Summary\nThe page passed every check.\n\n## Issues\nNo issues found."
    update, chat, _, _ = _write(make_llm, state, reply)
    assert "Score: 24/24 | Issues: 0 (high 0, medium 0, low 0)" in update["report"]
    assert "Findings (0)" in chat.calls[0][1].content


def test_eval_feedback_asks_for_exactly_those_fixes(make_llm) -> None:
    state = _state("page_seo.html")
    state["report"] = "# Landing Page Audit: page_seo.html\nScore: 18/24\n\n" + BODY
    state["eval_feedback"] = "SEO-07 is missing from the report."
    update, chat, _, _ = _write(make_llm, state, BODY + "\n### [medium] SEO-07")
    messages = chat.calls[0]
    assert len(messages) == 4
    assert isinstance(messages[2], AIMessage)
    assert messages[2].content == BODY
    assert "SEO-07 is missing from the report." in messages[3].content
    assert "Change exactly the points listed" in messages[3].content
    assert update["report"].count("# Landing Page Audit") == 1
    assert "### [medium] SEO-07" in update["report"]


def test_no_revision_messages_without_feedback(make_llm) -> None:
    state = _state("page_seo.html")
    state["eval_feedback"] = "  "
    _, chat, _, _ = _write(make_llm, state)
    assert len(chat.calls[0]) == 2
