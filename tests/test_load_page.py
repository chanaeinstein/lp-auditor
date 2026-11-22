"""Tests for load_page and extract_path (file IO only, no model)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.tools import MAX_PAGE_BYTES, PageError, extract_path, load_page


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("audit C:\\pages\\black-friday.html", "C:\\pages\\black-friday.html"),
        ("AUDIT   page.htm  ", "page.htm"),
        ('audit "C:\\My Pages\\lp.html"', "C:\\My Pages\\lp.html"),
        ("please check C:/sites/lp/index.html for SEO.", "C:/sites/lp/index.html"),
        ("Can you review ./landing.HTML?", "./landing.HTML"),
        ("check notes/readme.txt please", "notes/readme.txt"),
        ("please check my landing page", None),
        ("audit ", None),
    ],
)
def test_extract_path(message: str, expected: str | None) -> None:
    assert extract_path(message) == expected


def test_loads_utf8_page(tmp_path: Path) -> None:
    page = tmp_path / "lp.html"
    page.write_text("<title>שלום</title>", encoding="utf-8")
    path, html = load_page(str(page))
    assert path == page.resolve()
    assert html == "<title>שלום</title>"


def test_strips_utf8_bom_and_quotes(tmp_path: Path) -> None:
    page = tmp_path / "lp.HTM"
    page.write_bytes("\ufeff<p>x</p>".encode())
    _, html = load_page(f'"{page}"')
    assert html == "<p>x</p>"


def test_falls_back_to_cp1255(tmp_path: Path) -> None:
    page = tmp_path / "old.html"
    page.write_bytes("<p>עברית</p>".encode("cp1255"))
    _, html = load_page(str(page))
    assert html == "<p>עברית</p>"


def test_falls_back_to_latin1(tmp_path: Path) -> None:
    page = tmp_path / "odd.html"
    page.write_bytes(b"<p>\x81\x90</p>")  # undefined in cp1255 and invalid UTF-8
    _, html = load_page(str(page))
    assert html.startswith("<p>")


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(PageError, match="^File not found: .* - check the path"):
        load_page(str(tmp_path / "nope.html"))


def test_directory_is_not_a_file(tmp_path: Path) -> None:
    with pytest.raises(PageError, match="^File not found"):
        load_page(str(tmp_path))


def test_not_html(tmp_path: Path) -> None:
    page = tmp_path / "notes.txt"
    page.write_text("hi", encoding="utf-8")
    with pytest.raises(PageError, match="^Not an HTML file: notes.txt - give a .html"):
        load_page(str(page))


def test_too_big(tmp_path: Path) -> None:
    page = tmp_path / "big.html"
    page.write_bytes(b"x" * (MAX_PAGE_BYTES + 1))
    with pytest.raises(PageError, match="^File too big: .* the limit is 2 MB"):
        load_page(str(page))


def test_exactly_two_mb_is_allowed(tmp_path: Path) -> None:
    page = tmp_path / "edge.html"
    page.write_bytes(b"x" * MAX_PAGE_BYTES)
    _, html = load_page(str(page))
    assert len(html) == MAX_PAGE_BYTES
