"""Tests for run_checks: one or more positive and negative synthetic snippets per rule,
plus the fixture pages against evals/fixtures/expected.json (SEC-INJ comes from content_guard)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.tools import CHECKS, SNIPPET_MAX, load_rules, parse_rules, run_checks, score

FIXTURES = Path(__file__).resolve().parent.parent / "evals" / "fixtures"

HE_TITLE = "חשבון מסחר חדש עם בונוס הצטרפות לחודש נובמבר"  # 44 chars, 81 UTF-8 bytes
HE_DESC = "א" * 111  # 111 chars, 222 UTF-8 bytes

# (rule_id, html, expected number of findings for that rule). 0 = negative case.
CASES: list[tuple[str, str, int]] = [
    # SEO-01
    ("SEO-01", "<html><head></head><body></body></html>", 1),
    ("SEO-01", "<html><head><title>   </title></head></html>", 1),
    ("SEO-01", "<html><head><title>Hi</title></head></html>", 0),
    # SEO-02 (length in characters, not bytes)
    ("SEO-02", "<head><title>Short title here</title></head>", 1),
    ("SEO-02", f"<head><title>{'x' * 61}</title></head>", 1),
    ("SEO-02", f"<head><title>{HE_TITLE}</title></head>", 0),
    ("SEO-02", "<head><title>  Exactly   thirty characters long!  </title></head>", 0),
    ("SEO-02", "<head></head>", 0),
    # SEO-03
    ("SEO-03", "<head><title>t</title></head>", 1),
    ("SEO-03", '<head><meta name="description" content="   "></head>', 1),
    ("SEO-03", '<head><meta name="Description" content="Some text"></head>', 0),
    # SEO-04
    ("SEO-04", f'<head><meta name="description" content="{"x" * 69}"></head>', 1),
    ("SEO-04", f'<head><meta name="description" content="{"x" * 161}"></head>', 1),
    ("SEO-04", f'<head><meta name="description" content="{HE_DESC}"></head>', 0),
    ("SEO-04", '<head><meta name="description" content=""></head>', 0),
    # SEO-05
    ("SEO-05", "<body><h2>a</h2></body>", 1),
    ("SEO-05", "<body><h1>a</h1><h1>b</h1><h1>c</h1></body>", 1),
    ("SEO-05", "<body><h1>a</h1><h2>b</h2></body>", 0),
    # SEO-06
    ("SEO-06", "<h1>a</h1><h2>b</h2><h4>c</h4>", 1),
    ("SEO-06", "<h1>a</h1><h3>b</h3><h2>c</h2><h4>d</h4>", 2),
    (
        "SEO-06",
        "<h3>first heading is not checked</h3><h4>b</h4><h2>c</h2><h3>d</h3>",
        0,
    ),
    # SEO-07
    ("SEO-07", "<head></head>", 1),
    ("SEO-07", '<head><link rel="canonical" href=" "></head>', 1),
    ("SEO-07", '<head><link rel="canonicalx" href="https://e.com/"></head>', 1),
    (
        "SEO-07",
        '<head><link rel="Canonical alternate" href="https://e.com/"></head>',
        0,
    ),
    # SEO-08
    ("SEO-08", '<head><link rel="alternate" hreflang="en" href="/en"></head>', 1),
    (
        "SEO-08",
        (
            '<head><link rel="alternate" hreflang="en" href="/en">'
            '<link rel="alternate" hreflang="X-Default" href="/"></head>'
        ),
        0,
    ),
    ("SEO-08", '<head><link rel="alternate" href="/feed"></head>', 0),
    # SEO-09
    ("SEO-09", "<head></head>", 1),
    ("SEO-09", '<head><meta property="og:title" content="T"></head>', 1),
    (
        "SEO-09",
        '<head><meta property="og:title" content="T"><meta property="og:image" content=""></head>',
        1,
    ),
    (
        "SEO-09",
        '<head><meta property="og:title" content="T"><meta property="og:image" content="i.jpg"></head>',
        0,
    ),
    # A11Y-01
    ("A11Y-01", "<html><body></body></html>", 1),
    ("A11Y-01", '<html lang=" "></html>', 1),
    ("A11Y-01", '<html lang="en"></html>', 0),
    # A11Y-02
    ("A11Y-02", '<img src="a.png"><img src="b.png">', 2),
    ("A11Y-02", '<img src="a.png" alt="">', 0),
    # A11Y-03
    ("A11Y-03", '<a href="/x"><span class="icon"></span></a>', 1),
    ("A11Y-03", '<a href="/x"><span aria-hidden="true">Home</span></a>', 1),
    ("A11Y-03", '<a href="/x"><img src="i.svg" alt=""></a>', 1),
    ("A11Y-03", '<a href="/x" aria-labelledby="missing"></a>', 1),
    ("A11Y-03", '<a href="/x"><span class="sr-only">Home</span></a>', 0),
    ("A11Y-03", '<a href="/x" aria-label="Home"></a>', 0),
    ("A11Y-03", '<span id="l">Home</span><a href="/x" aria-labelledby="zz l"></a>', 0),
    ("A11Y-03", '<a href="/x"><img src="i.svg" alt="Home"></a>', 0),
    ("A11Y-03", '<a name="top"></a>', 0),
    # A11Y-04
    ("A11Y-04", '<button><svg aria-hidden="true"><path d="M0 0"/></svg></button>', 1),
    ("A11Y-04", '<div role="Button"></div><button role="button"></button>', 2),
    ("A11Y-04", '<button><span class="sr-only">Send</span></button>', 0),
    ("A11Y-04", '<button aria-label="Send"></button>', 0),
    # A11Y-05
    ("A11Y-05", '<input id="p" placeholder="Phone">', 1),
    ("A11Y-05", '<input type="TEXT"><select></select><textarea></textarea>', 3),
    ("A11Y-05", '<label for="P">Phone</label><input id="p">', 1),
    ("A11Y-05", '<label>Phone <input type="tel"></label>', 0),
    ("A11Y-05", '<label for="p">Phone</label><input id="p">', 0),
    ("A11Y-05", '<input aria-label="Phone"><input aria-labelledby="x">', 0),
    (
        "A11Y-05",
        (
            '<input type="HIDDEN"><input type="submit"><input type="button">'
            '<input type="reset"><input type="image" src="go.png">'
        ),
        0,
    ),
    # A11Y-06
    (
        "A11Y-06",
        '<meta name="viewport" content="width=device-width, user-scalable = NO">',
        1,
    ),
    (
        "A11Y-06",
        '<meta name="viewport" content="width=device-width,user-scalable=0">',
        1,
    ),
    (
        "A11Y-06",
        '<meta name="viewport" content="width=device-width, maximum-scale=1.5">',
        1,
    ),
    (
        "A11Y-06",
        '<meta name="viewport" content="width=device-width, maximum-scale=abc">',
        0,
    ),
    (
        "A11Y-06",
        '<meta name="viewport" content="width=device-width, maximum-scale=3">',
        0,
    ),
    (
        "A11Y-06",
        '<meta name="viewport" content="width=device-width, user-scalable=yes">',
        0,
    ),
    # A11Y-07
    ("A11Y-07", '<input tabindex=" 2"><div tabindex="5"></div>', 2),
    ("A11Y-07", '<a tabindex="0"></a><a tabindex="-1"></a><a tabindex="abc"></a>', 0),
    # A11Y-08
    ("A11Y-08", '<a href="/a">Read more…</a>', 1),
    ("A11Y-08", '<a href="/a">  Click\n   HERE! </a>', 1),
    ("A11Y-08", '<a href="/a">לחצו כאן</a><a href="/b">(קראו עוד)</a>', 2),
    ("A11Y-08", '<a href="/a" aria-label="Bonus terms">here</a>', 0),
    ("A11Y-08", '<a href="/a">here are the terms</a>', 0),
    # A11Y-09
    ("A11Y-09", '<input id="mail"><section id="mail"></section><p id="mail"></p>', 1),
    ("A11Y-09", '<p id="a"></p><p id="a"></p><p id="b"></p><p id="b"></p>', 2),
    ("A11Y-09", '<p id="x"></p><p id="X"></p><p id=""></p><p id=""></p>', 0),
    # PERF-01
    ("PERF-01", '<img src="a" alt="" width="10">', 1),
    ("PERF-01", '<img src="a" alt="" width="" height="10">', 1),
    ("PERF-01", '<img src="a" alt="" width="10" height="10">', 0),
    # PERF-02
    (
        "PERF-02",
        '<img src="1"><img src="2"><img src="3"><img src="4" loading="lazy">',
        1,
    ),
    (
        "PERF-02",
        '<img src="1"><img src="2"><img src="3" loading="eager"><img src="4">',
        2,
    ),
    ("PERF-02", '<img src="1"><img src="2"><img src="3" loading="LAZY">', 0),
    ("PERF-02", '<img src="1"><img src="2">', 0),
    # PERF-03
    (
        "PERF-03",
        '<head><script src="a.js"></script><script src="b.js"></script></head>',
        2,
    ),
    (
        "PERF-03",
        (
            '<head><script src="a.js" defer></script><script src="b.js" async></script>'
            '<script src="c.js" type="Module"></script><script>var x = 1;</script></head>'
            '<body><script src="d.js"></script></body>'
        ),
        0,
    ),
    # PERF-04
    ("PERF-04", '<img src="hero" loading="lazy"><img src="2">', 1),
    ("PERF-04", '<img src="hero"><img src="2" loading="lazy">', 0),
    # I18N-01
    ("I18N-01", '<html lang="he-IL"></html>', 1),
    ("I18N-01", '<html lang="AR" dir="ltr"></html>', 1),
    ("I18N-01", '<html lang="iw"></html>', 1),
    ("I18N-01", '<html lang="he" dir="RTL"></html>', 0),
    ("I18N-01", '<html lang="hr"></html>', 0),
    ("I18N-01", '<html lang="en"></html>', 0),
    # SEC-01
    ("SEC-01", '<a href="/x" target="_BLANK">x</a>', 1),
    ("SEC-01", '<a href="/x" target="_blank" rel="noopenerx">x</a>', 1),
    ("SEC-01", '<a href="/x" target="_blank" rel="external noreferrer">x</a>', 0),
    ("SEC-01", '<a href="/x" target="_self">x</a>', 0),
]


def _count(html: str, rule_id: str) -> int:
    return sum(1 for f in run_checks(html) if f["rule_id"] == rule_id)


@pytest.mark.parametrize(
    ("rule_id", "html", "expected"),
    CASES,
    ids=[f"{rule}-{'pos' if n else 'neg'}-{i}" for i, (rule, _, n) in enumerate(CASES)],
)
def test_rule_case(rule_id: str, html: str, expected: int) -> None:
    assert _count(html, rule_id) == expected


def test_every_detection_rule_has_a_check_and_both_kinds_of_case() -> None:
    detection_rules = {r.rule_id for r in load_rules().values() if r.has_detection}
    assert detection_rules == set(CHECKS)
    assert len(detection_rules) == 24
    positives = {rule for rule, _, n in CASES if n > 0}
    negatives = {rule for rule, _, n in CASES if n == 0}
    assert positives == detection_rules
    assert negatives == detection_rules


def test_sec_inj_is_not_a_run_checks_rule() -> None:
    rules = load_rules()
    assert rules["SEC-INJ"].severity == "high"
    assert not rules["SEC-INJ"].has_detection


EXPECTED = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("page", sorted(EXPECTED))
def test_fixture_pages_match_expected(page: str) -> None:
    findings = run_checks((FIXTURES / page).read_text(encoding="utf-8"))
    expected = set(EXPECTED[page]["rule_ids"]) - {"SEC-INJ"}
    assert {f["rule_id"] for f in findings} == expected


def test_finding_shape_and_severity_come_from_rules() -> None:
    findings = run_checks((FIXTURES / "page_a11y.html").read_text(encoding="utf-8"))
    rules = load_rules()
    for f in findings:
        assert set(f) == {"rule_id", "severity", "element", "detail"}
        assert f["severity"] == rules[f["rule_id"]].severity
        assert 0 < len(f["element"]) <= SNIPPET_MAX
        assert f["detail"]


def test_long_element_is_cut_to_200_chars() -> None:
    html = f'<a href="/x"><span class="{"c" * 500}"></span></a>'
    (finding,) = [f for f in run_checks(html) if f["rule_id"] == "A11Y-03"]
    assert len(finding["element"]) == SNIPPET_MAX
    assert finding["element"].endswith("...")


def test_missing_element_quotes_head_start_tag() -> None:
    (finding,) = [
        f for f in run_checks("<html><head></head></html>") if f["rule_id"] == "SEO-01"
    ]
    assert finding["element"] == "<head>"


def test_score_counts_failed_rules_once() -> None:
    clean = run_checks((FIXTURES / "page_clean.html").read_text(encoding="utf-8"))
    assert score(clean) == (24, 24)
    two_imgs = run_checks('<html lang="en"><img src="a"><img src="b"></html>')
    passed, total = score(two_imgs)
    assert total == 24
    assert passed == total - len({f["rule_id"] for f in two_imgs})


def test_parse_rules_reads_fields() -> None:
    rules = parse_rules(
        "# T\n\nintro\n\n## SEO\n\n### X-01 Some title\nSeverity: Medium\n"
        "Detection: something.\nWhy: w\n\n### X-02 Other\nSeverity: low\n"
        "Detection: by the `content_guard` node (LLM), not by `run_checks`.\n"
    )
    assert list(rules) == ["X-01", "X-02"]
    assert rules["X-01"].title == "Some title"
    assert rules["X-01"].severity == "medium"
    assert rules["X-01"].has_detection
    assert not rules["X-02"].has_detection
