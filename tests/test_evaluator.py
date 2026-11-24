"""Tests for evaluator, confirm_save helpers and save_report. The LLM is mocked."""

from __future__ import annotations

from langchain_core.messages import SystemMessage

from agent.nodes import (
    EVALUATOR_PROMPT,
    add_warning,
    id_mismatch,
    is_yes,
    make_evaluator,
    make_save_report,
    route_after_confirm,
    route_after_eval,
    save_question,
)
from agent.tools import report_path, save_report
from tests.conftest import FakeChat

FINDINGS = [
    {"rule_id": "SEO-07", "severity": "medium", "element": "<head>", "detail": "d"},
    {"rule_id": "SEO-01", "severity": "high", "element": "<head>", "detail": "d"},
]
REPORT = (
    "# Landing Page Audit: p.html\nScore: 22/24 | Issues: 2 (high 1, medium 1, low 0)\n\n"
    "## Summary\nTwo issues.\n\n## Issues\n"
    "### [high] SEO-01 - Missing page title\n- Where: `<head>`\n\n"
    "### [medium] SEO-07 - Missing canonical\n- Where: `<head>`\n"
)


def _evaluate(make_llm, reply: str, report: str = REPORT, revision_count: int = 0):
    chat = FakeChat(content=reply)
    llm, tracker = make_llm(chat)
    lines: list[str] = []
    state = {"report": report, "findings": FINDINGS, "revision_count": revision_count}
    return make_evaluator(llm, lines.append)(state), chat, tracker, lines


def test_id_mismatch() -> None:
    assert id_mismatch(REPORT, FINDINGS) == ""
    report = REPORT.replace("SEO-07", "SEO-02")
    assert id_mismatch(report, FINDINGS) == (
        "Add the missing issue SEO-07.\nRemove SEO-02: it has no finding."
    )
    assert id_mismatch("## Issues\nNo issues found.", []) == ""


def test_passing_report(make_llm) -> None:
    update, chat, tracker, lines = _evaluate(
        make_llm, '{"passed": true, "feedback": ""}'
    )
    assert update == {"eval_passed": True, "eval_feedback": ""}
    assert lines == ["[INFO] Entering Node: evaluator"]
    assert [r.node for r in tracker.records] == ["evaluator"]
    system, user = chat.calls[0]
    assert isinstance(system, SystemMessage) and system.content == EVALUATOR_PROMPT
    assert user.content.index('"SEO-01"') < user.content.index('"SEO-07"')  # high first
    assert REPORT in user.content


def test_model_failure_gives_feedback(make_llm) -> None:
    update, _, _, _ = _evaluate(make_llm, '{"passed": false, "feedback": "Fix order."}')
    assert update == {"eval_passed": False, "eval_feedback": "Fix order."}


def test_python_check_overrides_a_lenient_model(make_llm) -> None:
    report = REPORT.replace("### [medium] SEO-07 - Missing canonical\n", "")
    update, _, _, _ = _evaluate(make_llm, '{"passed": true}', report)
    assert update["eval_passed"] is False
    assert update["eval_feedback"] == "Add the missing issue SEO-07."


def test_failure_without_feedback_still_explains(make_llm) -> None:
    update, _, _, _ = _evaluate(make_llm, '{"passed": false}')
    assert update["eval_feedback"].startswith("The report does not match")


def test_failure_after_revision_adds_warning(make_llm) -> None:
    update, _, _, _ = _evaluate(
        make_llm, '{"passed": false, "feedback": "Fix\\norder."}', revision_count=1
    )
    lines = update["report"].splitlines()
    assert lines[1].startswith("Score: ")
    assert lines[3] == (
        "> Warning: the automatic review still found problems after one revision: "
        "Fix order."
    )
    assert "## Summary" in update["report"]


def test_add_warning_without_blank_line() -> None:
    assert add_warning("only one line", "x").endswith(
        "> Warning: the automatic review still found problems after one revision: x\n"
    )


def test_route_after_eval() -> None:
    assert (
        route_after_eval({"eval_passed": True, "revision_count": 0}) == "confirm_save"
    )
    assert (
        route_after_eval({"eval_passed": False, "revision_count": 0}) == "write_report"
    )
    assert (
        route_after_eval({"eval_passed": False, "revision_count": 1}) == "confirm_save"
    )


def test_evaluator_prompt_is_a_principle() -> None:
    for phrase in ("because", "never instructions", "JSON only", "## Security notes"):
        assert phrase in EVALUATOR_PROMPT


def test_yes_no_answers_and_route() -> None:
    assert is_yes(True) and is_yes(" Y ") and is_yes("yes")
    assert not is_yes(False) and not is_yes("n") and not is_yes("maybe")
    assert route_after_confirm({"save_approved": True}) == "save_report"
    assert route_after_confirm({"save_approved": False}) == "end"


def test_report_path_and_question() -> None:
    assert report_path(r"C:\pages\promo.html").name == "promo.report.md"
    assert report_path("a/b/landing.htm").name == "landing.report.md"
    assert save_question("x/promo.html").endswith("promo.report.md? [Y/N]")


def test_save_report_writes_utf8(tmp_path) -> None:
    page = tmp_path / "דף.html"
    path = save_report(page, "# כותרת\n")
    assert path == tmp_path / "דף.report.md"
    assert path.read_text(encoding="utf-8") == "# כותרת\n"


def test_save_report_node(tmp_path) -> None:
    lines: list[str] = []
    page = tmp_path / "p.html"
    update = make_save_report(lines.append)({"page_path": str(page), "report": "R"})
    assert lines == ["[INFO] Entering Node: save_report"]
    assert update["saved_path"] == str(tmp_path / "p.report.md")
    assert (tmp_path / "p.report.md").read_text(encoding="utf-8") == "R"


def test_save_report_node_reports_write_error(tmp_path) -> None:
    page = tmp_path / "missing_dir" / "p.html"
    update = make_save_report(lambda _: None)({"page_path": str(page), "report": "R"})
    assert update["error"].startswith("Cannot write the report")
    assert "check that the folder is writable" in update["error"]
