"""Tests for BM25 rule retrieval in agent/tools.py. No model is called."""

from __future__ import annotations

from agent.tools import (
    build_index,
    free_text,
    load_rules,
    parse_rules,
    retrieve_rules,
    rule_index,
    tokenize,
)

MINI_RULES = """\
# Rules

### R-1 Missing title
Severity: high
Detection: no title.
Why: Search results need a title.
Fix: Add a title.

### R-2 Image without alt
Severity: high
Detection: img without alt.
Why: Screen readers read the file name.
Fix: Add alt text to the image.

### R-3 Duplicate id
Severity: medium
Detection: same id twice.
Why: Labels point to the first match only.
Fix: Make every id unique.
"""


def _finding(rule_id: str) -> dict:
    return {"rule_id": rule_id, "severity": "high", "element": "<x>", "detail": "d"}


def _ids(chunks: list[str]) -> list[str]:
    return [c.split()[1] for c in chunks]


def test_tokenize_keeps_hebrew_and_lowercases() -> None:
    assert tokenize("Click HERE, לחצו כאן!") == ["click", "here", "לחצו", "כאן"]


def test_index_has_one_chunk_per_rule_heading() -> None:
    index = rule_index()
    assert index.ids == list(load_rules())
    assert "SEC-INJ" in index.ids
    assert all(t.startswith("### ") for t in index.texts)


def test_found_rules_are_taken_by_id_in_finding_order_without_duplicates() -> None:
    index = build_index(parse_rules(MINI_RULES))
    findings = [_finding("R-3"), _finding("R-1"), _finding("R-3")]
    assert _ids(retrieve_rules(findings, "", index)) == ["R-3", "R-1"]


def test_unknown_rule_id_is_skipped() -> None:
    index = build_index(parse_rules(MINI_RULES))
    assert retrieve_rules([_finding("NOPE-1")], "", index) == []


def test_free_text_adds_top_bm25_chunks_after_found_rules() -> None:
    index = build_index(parse_rules(MINI_RULES))
    chunks = retrieve_rules(
        [_finding("R-1")], "why does alt text on an image matter?", index
    )
    assert _ids(chunks) == ["R-1", "R-2"]


def test_free_text_without_matching_terms_adds_nothing() -> None:
    index = build_index(parse_rules(MINI_RULES))
    assert retrieve_rules([], "audit", index) == []
    assert index.search("") == []


def test_search_returns_at_most_three() -> None:
    hits = rule_index().search("image alt link button label title description heading")
    assert 1 <= len(hits) <= 3


def test_free_text_removes_the_page_path() -> None:
    message = r"audit C:\pages\landing.html and explain the alt problems"
    assert free_text(message) == "audit and explain the alt problems"
    assert "landing" not in free_text(message)


def test_real_rule_base_finds_tabnabbing_rule_for_question() -> None:
    chunks = retrieve_rules(
        [], r"audit C:\p\a.html - what is window.opener tabnabbing?"
    )
    assert _ids(chunks)[0] == "SEC-01"
