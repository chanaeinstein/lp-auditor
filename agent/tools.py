"""Tools: load_page, run_checks, rule-base access. BM25 retrieval and cost helpers arrive on day 4.

Every check here is plain Python and follows the Detection line of its rule in
agent/knowledge/rules.md exactly. Keep the two in sync.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from agent.models import resource_path

MAX_PAGE_BYTES = 2 * 1024 * 1024
HTML_SUFFIXES = (".html", ".htm")
FALLBACK_ENCODINGS = ("utf-8-sig", "cp1255", "latin-1")
SNIPPET_MAX = 200

Finding = dict[str, Any]


# --------------------------------------------------------------------------- rules.md


@dataclass(frozen=True)
class Rule:
    rule_id: str
    title: str
    severity: str
    has_detection: bool
    text: str


RULE_HEADING = re.compile(r"^###\s+(\S+)\s+(.+?)\s*$")


def parse_rules(markdown: str) -> dict[str, Rule]:
    """Split rules.md on `### ` headings into Rule records, in file order."""
    rules: dict[str, Rule] = {}
    for chunk in re.split(r"(?m)^(?=### )", markdown):
        lines = chunk.strip().splitlines()
        if not lines:
            continue
        match = RULE_HEADING.match(lines[0])
        if not match:
            continue
        fields = {
            key.strip().lower(): value.strip()
            for key, _, value in (line.partition(":") for line in lines[1:])
        }
        rules[match.group(1)] = Rule(
            rule_id=match.group(1),
            title=match.group(2),
            severity=fields.get("severity", "").lower(),
            has_detection="run_checks" not in fields.get("detection", "run_checks"),
            text=chunk.strip(),
        )
    return rules


@lru_cache(maxsize=1)
def load_rules() -> dict[str, Rule]:
    path = resource_path("agent/knowledge/rules.md")
    return parse_rules(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- load_page


class PageError(Exception):
    """The page cannot be loaded. The message is one line: what happened - what to do."""


QUOTED_PATH = re.compile(r"[\"']([^\"']+)[\"']")
HTML_PATH = re.compile(r"[^\s\"'<>|]+\.html?\b", re.IGNORECASE)
ANY_FILE_PATH = re.compile(r"[^\s\"'<>|]*[\\/:.][^\s\"'<>|]*\.[A-Za-z0-9]{1,5}\b")


def extract_path(message: str) -> str | None:
    """Find the page path in `audit <path>` or in a free-text message."""
    text = message.strip()
    quoted = QUOTED_PATH.search(text)
    if quoted:
        return quoted.group(1).strip()
    if text.lower().startswith("audit "):
        return text[len("audit ") :].strip() or None
    for pattern in (HTML_PATH, ANY_FILE_PATH):
        match = pattern.search(text)
        if match:
            return match.group(0).rstrip(".,;:!?)")
    return None


def decode_html(data: bytes) -> str:
    """UTF-8 first, then cp1255 (Hebrew Windows); latin-1 accepts any byte, so it is last."""
    for encoding in FALLBACK_ENCODINGS[:-1]:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode(FALLBACK_ENCODINGS[-1])


def load_page(raw_path: str) -> tuple[Path, str]:
    """Validate and read a local HTML file. Raises PageError with a one-line message."""
    path = Path(raw_path.strip().strip("\"'")).expanduser()
    if not path.is_file():
        raise PageError(f"File not found: {path} - check the path and try again")
    if path.suffix.lower() not in HTML_SUFFIXES:
        raise PageError(f"Not an HTML file: {path.name} - give a .html or .htm file")
    size = path.stat().st_size
    if size > MAX_PAGE_BYTES:
        raise PageError(
            f"File too big: {size / 1024 / 1024:.1f} MB - the limit is 2 MB, "
            "audit a smaller page"
        )
    return path.resolve(), decode_html(path.read_bytes())


# --------------------------------------------------------------------------- helpers


def norm(text: str) -> str:
    """Trim and collapse internal whitespace (rules.md: Text)."""
    return " ".join(text.split())


def attr(el: Tag, name: str) -> str | None:
    value = el.get(name)
    if value is None:
        return None
    return value if isinstance(value, str) else " ".join(value)


def attr_lower(el: Tag, name: str) -> str:
    return (attr(el, name) or "").strip().lower()


def tokens(el: Tag, name: str) -> set[str]:
    return set(attr_lower(el, name).split())


def is_hidden(el: Tag) -> bool:
    return attr_lower(el, "aria-hidden") == "true" or el.has_attr("hidden")


def walk_visible(el: Tag) -> Iterator[Tag | NavigableString]:
    """Descendants of el, skipping hidden subtrees, script, style and comments."""
    for child in el.children:
        if isinstance(child, Tag):
            if is_hidden(child) or child.name in ("script", "style"):
                continue
            yield child
            yield from walk_visible(child)
        elif isinstance(child, NavigableString) and not isinstance(child, Comment):
            yield child


def text_of(el: Tag) -> str:
    return norm(
        "".join(str(n) for n in walk_visible(el) if isinstance(n, NavigableString))
    )


def has_accessible_name(el: Tag, soup: BeautifulSoup) -> bool:
    """rules.md: Accessible name."""
    if text_of(el):
        return True
    if norm(attr(el, "aria-label") or ""):
        return True
    for ref_id in (attr(el, "aria-labelledby") or "").split():
        ref = soup.find(id=ref_id)
        if isinstance(ref, Tag) and text_of(ref):
            return True
    return any(
        isinstance(n, Tag) and n.name == "img" and norm(attr(n, "alt") or "")
        for n in walk_visible(el)
    )


def start_tag(el: Tag | None, fallback: str = "") -> str:
    if el is None:
        return fallback
    parts = [el.name]
    for name, value in el.attrs.items():
        value = value if isinstance(value, str) else " ".join(value)
        parts.append(f'{name}="{value}"')
    return cut("<" + " ".join(parts) + ">")


def cut(text: str) -> str:
    text = norm(text)
    return text if len(text) <= SNIPPET_MAX else text[: SNIPPET_MAX - 3] + "..."


def snippet(el: Tag) -> str:
    return cut(str(el))


def strip_punctuation(text: str) -> str:
    start, end = 0, len(text)
    while start < end and unicodedata.category(text[start]).startswith("P"):
        start += 1
    while end > start and unicodedata.category(text[end - 1]).startswith("P"):
        end -= 1
    return text[start:end].strip()


# --------------------------------------------------------------------------- checks


@dataclass
class Page:
    soup: BeautifulSoup

    @property
    def html(self) -> Tag | None:
        tag = self.soup.find("html")
        return tag if isinstance(tag, Tag) else None

    @property
    def head(self) -> Tag | None:
        return self.soup.head

    def head_tag(self) -> str:
        return start_tag(self.head, start_tag(self.html, "<head>"))

    def html_tag(self) -> str:
        return start_tag(self.html, "<html>")

    def body_tag(self) -> str:
        return start_tag(self.soup.body, self.html_tag())

    def all(self, *names: str) -> list[Tag]:
        return [t for t in self.soup.find_all(list(names)) if isinstance(t, Tag)]

    def meta(self, key: str, value: str) -> Tag | None:
        for tag in self.all("meta"):
            if attr_lower(tag, key) == value:
                return tag
        return None


Hit = tuple[str, str]  # (element snippet, detail)
Check = Callable[[Page], list[Hit]]
CHECKS: dict[str, Check] = {}


def check(rule_id: str) -> Callable[[Check], Check]:
    def register(fn: Check) -> Check:
        CHECKS[rule_id] = fn
        return fn

    return register


def _title(page: Page) -> Tag | None:
    if page.head is None:
        return None
    tag = page.head.find("title")
    return tag if isinstance(tag, Tag) else None


@check("SEO-01")
def seo_01(page: Page) -> list[Hit]:
    title = _title(page)
    if title is None:
        return [(page.head_tag(), "The page has no <title> in <head>.")]
    if not norm(title.get_text()):
        return [(page.head_tag(), "The <title> is empty.")]
    return []


@check("SEO-02")
def seo_02(page: Page) -> list[Hit]:
    title = _title(page)
    text = norm(title.get_text()) if title else ""
    if text and not 30 <= len(text) <= 60:
        return [
            (snippet(title), f"The title has {len(text)} characters; aim for 30-60.")
        ]
    return []


def _description(page: Page) -> tuple[Tag | None, str]:
    tag = page.meta("name", "description")
    return tag, norm(attr(tag, "content") or "") if tag else ""


@check("SEO-03")
def seo_03(page: Page) -> list[Hit]:
    tag, content = _description(page)
    if tag is None:
        return [(page.head_tag(), 'The page has no <meta name="description">.')]
    if not content:
        return [(page.head_tag(), "The meta description content is empty.")]
    return []


@check("SEO-04")
def seo_04(page: Page) -> list[Hit]:
    tag, content = _description(page)
    if tag is not None and content and not 70 <= len(content) <= 160:
        return [
            (
                snippet(tag),
                f"The meta description has {len(content)} characters; aim for 70-160.",
            )
        ]
    return []


@check("SEO-05")
def seo_05(page: Page) -> list[Hit]:
    h1s = page.all("h1")
    if len(h1s) == 1:
        return []
    element = snippet(h1s[1]) if len(h1s) > 1 else page.body_tag()
    return [
        (element, f"The page has {len(h1s)} <h1> elements; it should have exactly 1.")
    ]


@check("SEO-06")
def seo_06(page: Page) -> list[Hit]:
    headings = page.all("h1", "h2", "h3", "h4", "h5", "h6")
    hits: list[Hit] = []
    for prev, cur in pairwise(headings):
        prev_level, cur_level = int(prev.name[1]), int(cur.name[1])
        if cur_level > prev_level + 1:
            hits.append(
                (
                    snippet(cur),
                    f"<{cur.name}> follows <{prev.name}>; level {prev_level + 1} is skipped.",
                )
            )
    return hits


def _links_with_rel(page: Page, token: str) -> list[Tag]:
    return [t for t in page.all("link") if token in tokens(t, "rel")]


@check("SEO-07")
def seo_07(page: Page) -> list[Hit]:
    if any(norm(attr(t, "href") or "") for t in _links_with_rel(page, "canonical")):
        return []
    return [(page.head_tag(), 'The page has no <link rel="canonical"> with an href.')]


@check("SEO-08")
def seo_08(page: Page) -> list[Hit]:
    alternates = [
        t for t in _links_with_rel(page, "alternate") if t.has_attr("hreflang")
    ]
    if alternates and not any(
        attr_lower(t, "hreflang") == "x-default" for t in alternates
    ):
        return [
            (
                page.head_tag(),
                f'{len(alternates)} hreflang alternate link(s) but none with hreflang="x-default".',
            )
        ]
    return []


@check("SEO-09")
def seo_09(page: Page) -> list[Hit]:
    missing = []
    for prop in ("og:title", "og:image"):
        tag = page.meta("property", prop)
        if tag is None or not norm(attr(tag, "content") or ""):
            missing.append(prop)
    if missing:
        return [
            (
                page.head_tag(),
                "Missing or empty Open Graph tags: " + ", ".join(missing) + ".",
            )
        ]
    return []


@check("A11Y-01")
def a11y_01(page: Page) -> list[Hit]:
    if page.html is None or not attr_lower(page.html, "lang"):
        return [(page.html_tag(), "The <html> element has no lang attribute.")]
    return []


@check("A11Y-02")
def a11y_02(page: Page) -> list[Hit]:
    return [
        (snippet(img), "The image has no alt attribute.")
        for img in page.all("img")
        if not img.has_attr("alt")
    ]


@check("A11Y-03")
def a11y_03(page: Page) -> list[Hit]:
    return [
        (snippet(a), "The link has no accessible name.")
        for a in page.all("a")
        if a.has_attr("href") and not has_accessible_name(a, page.soup)
    ]


@check("A11Y-04")
def a11y_04(page: Page) -> list[Hit]:
    buttons = [
        t
        for t in page.soup.find_all(True)
        if isinstance(t, Tag)
        and (t.name == "button" or attr_lower(t, "role") == "button")
    ]
    return [
        (snippet(b), "The button has no accessible name.")
        for b in buttons
        if not has_accessible_name(b, page.soup)
    ]


FIELD_EXEMPT_TYPES = {"hidden", "submit", "button", "reset", "image"}


@check("A11Y-05")
def a11y_05(page: Page) -> list[Hit]:
    label_targets = {attr(lb, "for") for lb in page.all("label") if attr(lb, "for")}
    hits: list[Hit] = []
    for field in page.all("input", "select", "textarea"):
        if (
            field.name == "input"
            and (attr_lower(field, "type") or "text") in FIELD_EXEMPT_TYPES
        ):
            continue
        labelled = (
            norm(attr(field, "aria-label") or "")
            or norm(attr(field, "aria-labelledby") or "")
            or field.find_parent("label") is not None
            or (attr(field, "id") is not None and attr(field, "id") in label_targets)
        )
        if not labelled:
            hits.append((snippet(field), "The form field has no label."))
    return hits


@check("A11Y-06")
def a11y_06(page: Page) -> list[Hit]:
    tag = page.meta("name", "viewport")
    if tag is None:
        return []
    settings: dict[str, str] = {}
    for pair in (attr(tag, "content") or "").split(","):
        key, _, value = pair.partition("=")
        settings[key.strip().lower()] = value.strip().lower()
    problems = []
    if settings.get("user-scalable") in ("no", "0"):
        problems.append(f"user-scalable={settings['user-scalable']}")
    try:
        if float(settings.get("maximum-scale", "")) < 2:
            problems.append(f"maximum-scale={settings['maximum-scale']}")
    except ValueError:
        pass
    if problems:
        return [(snippet(tag), "Zoom is limited by " + ", ".join(problems) + ".")]
    return []


@check("A11Y-07")
def a11y_07(page: Page) -> list[Hit]:
    hits: list[Hit] = []
    for el in page.soup.find_all(attrs={"tabindex": True}):
        try:
            value = int((attr(el, "tabindex") or "").strip())
        except ValueError:
            continue
        if value > 0:
            hits.append((snippet(el), f"tabindex={value} forces a custom tab order."))
    return hits


GENERIC_LINK_TEXTS = {
    "click here",
    "here",
    "read more",
    "more",
    "learn more",
    "לחצו כאן",
    "לחץ כאן",
    "כאן",
    "קרא עוד",
    "קראו עוד",
    "למידע נוסף",
}


@check("A11Y-08")
def a11y_08(page: Page) -> list[Hit]:
    hits: list[Hit] = []
    for a in page.all("a"):
        if norm(attr(a, "aria-label") or ""):
            continue
        text = strip_punctuation(text_of(a)).lower()
        if text in GENERIC_LINK_TEXTS:
            hits.append(
                (snippet(a), f'The link text "{text}" does not name the destination.')
            )
    return hits


@check("A11Y-09")
def a11y_09(page: Page) -> list[Hit]:
    by_id: dict[str, list[Tag]] = {}
    for el in page.soup.find_all(attrs={"id": True}):
        value = attr(el, "id") or ""
        if value.strip():
            by_id.setdefault(value, []).append(el)
    return [
        (snippet(elements[1]), f'id="{value}" is used by {len(elements)} elements.')
        for value, elements in by_id.items()
        if len(elements) > 1
    ]


@check("PERF-01")
def perf_01(page: Page) -> list[Hit]:
    return [
        (snippet(img), "The image has no width and/or height attribute.")
        for img in page.all("img")
        if not (attr(img, "width") or "").strip()
        or not (attr(img, "height") or "").strip()
    ]


@check("PERF-02")
def perf_02(page: Page) -> list[Hit]:
    return [
        (snippet(img), f'Image #{index} is not loading="lazy".')
        for index, img in enumerate(page.all("img"), start=1)
        if index >= 3 and attr_lower(img, "loading") != "lazy"
    ]


@check("PERF-03")
def perf_03(page: Page) -> list[Hit]:
    if page.head is None:
        return []
    return [
        (
            snippet(s),
            "The script in <head> blocks rendering (no defer, async or type=module).",
        )
        for s in page.head.find_all("script")
        if isinstance(s, Tag)
        and s.has_attr("src")
        and not s.has_attr("defer")
        and not s.has_attr("async")
        and attr_lower(s, "type") != "module"
    ]


@check("PERF-04")
def perf_04(page: Page) -> list[Hit]:
    images = page.all("img")
    if images and attr_lower(images[0], "loading") == "lazy":
        return [(snippet(images[0]), 'The first image has loading="lazy".')]
    return []


RTL_LANGUAGES = {"he", "iw", "ar", "fa", "ur", "yi"}


@check("I18N-01")
def i18n_01(page: Page) -> list[Hit]:
    if page.html is None:
        return []
    lang = attr_lower(page.html, "lang")
    primary = lang.split("-")[0]
    if primary in RTL_LANGUAGES and attr_lower(page.html, "dir") != "rtl":
        return [
            (
                page.html_tag(),
                f'lang="{lang}" is right-to-left but <html> has no dir="rtl".',
            )
        ]
    return []


@check("SEC-01")
def sec_01(page: Page) -> list[Hit]:
    return [
        (snippet(a), 'target="_blank" without rel="noopener".')
        for a in page.all("a")
        if attr_lower(a, "target") == "_blank"
        and not tokens(a, "rel") & {"noopener", "noreferrer"}
    ]


def parse_html(html: str) -> Page:
    # multi_valued_attributes=None keeps class/rel as plain strings, so attr() is uniform.
    return Page(BeautifulSoup(html, "html.parser", multi_valued_attributes=None))


def run_checks(html: str) -> list[Finding]:
    """Run every rule that has a Detection line, in rules.md order."""
    rules = load_rules()
    page = parse_html(html)
    findings: list[Finding] = []
    for rule_id, rule in rules.items():
        if not rule.has_detection:
            continue
        for element, detail in CHECKS[rule_id](page):
            findings.append(
                {
                    "rule_id": rule_id,
                    "severity": rule.severity,
                    "element": element,
                    "detail": detail,
                }
            )
    return findings


def score(findings: list[Finding]) -> tuple[int, int]:
    """(passed checks, total checks) as defined in rules.md: Score."""
    checked = {r.rule_id for r in load_rules().values() if r.has_detection}
    failed = {f["rule_id"] for f in findings} & checked
    return len(checked) - len(failed), len(checked)
