# Landing Page Audit Rules

Each rule has: Severity, Detection (implemented in plain Python in `run_checks`, exactly as written), Findings (how many findings the rule produces and which element each one quotes), Why, Fix.

Definitions used by every Detection line:

- Text: the text content of an element, ignoring descendants that have `aria-hidden="true"` or the `hidden` attribute, and ignoring `<script>` and `<style>`. Whitespace is trimmed at both ends and internal runs of whitespace are collapsed to one space.
- Length: counted in Unicode characters of the text after the normalization above, never in bytes.
- Matching: text, attribute names and enumerated attribute values (for example `type`, `target`, `dir`, `rel`, `loading`) are compared case-insensitively.
- Token list: `rel` is split on whitespace and compared as whole tokens; "contains `noopener`" means one of the tokens equals `noopener`.
- Accessible name: non-empty text; or a non-empty `aria-label`; or `aria-labelledby` (a space-separated list of ids) where at least one referenced element exists and has non-empty text; or, for links and buttons containing an image, an `<img>` with non-empty `alt`.
- Element: each finding quotes the offending element's HTML, cut to 200 characters. When the problem is something missing, it quotes the start tag of the place where it should be (`<head>`, `<html ...>` or `<body ...>`), as stated in each rule's Findings line.
- Score: the total number of checks is the number of rules with a Detection line run by `run_checks` (24; `SEC-INJ` is not counted). A check passes when it produced no findings. A check whose condition does not apply (for example SEO-02 when there is no title) passes.

## SEO

### SEO-01 Missing page title
Severity: high
Detection: no `<title>` in `<head>`, or its text is empty.
Findings: one per page; element: the `<head>` start tag.
Why: The title is the main line shown in search results and browser tabs. Without it search engines invent one and click-through drops.
Fix: Add a unique `<title>` that states the offer, 30-60 characters.

### SEO-02 Title length out of range
Severity: low
Detection: `<title>` text is not empty and its length is below 30 or above 60 characters.
Findings: one per page; element: the `<title>` element.
Why: Short titles waste the space in search results; long ones are cut off, often in the middle of the offer.
Fix: Rewrite the title to 30-60 characters, with the main keyword near the start.

### SEO-03 Missing meta description
Severity: medium
Detection: no `<meta name="description">`, or its `content` is empty after trimming.
Findings: one per page; element: the `<head>` start tag.
Why: Search engines use it as the snippet under the title. Without it they take random page text.
Fix: Add a `<meta name="description">` of 70-160 characters that summarizes the offer and the call to action.

### SEO-04 Meta description length out of range
Severity: low
Detection: meta description `content` is not empty and its length is below 70 or above 160 characters.
Findings: one per page; element: the `<meta name="description">` element.
Why: Too short gives users no reason to click; too long is cut off.
Fix: Rewrite it to 70-160 characters.

### SEO-05 Not exactly one H1
Severity: medium
Detection: the number of `<h1>` elements is not 1.
Findings: one per page, the detail states the count; element: the second `<h1>` if there are several, or the `<body>` start tag if there is none.
Why: One H1 tells search engines and screen-reader users what the page is about. Zero or several H1s blur the main topic.
Fix: Keep a single H1 with the main message; turn the others into H2.

### SEO-06 Skipped heading level
Severity: low
Detection: walking all `h1`-`h6` in document order, starting from the second heading, a heading's level is more than one deeper than the previous heading's level (for example `h2` followed by `h4`). The first heading on the page is not checked.
Findings: one per occurrence of a jump; element: the deeper heading.
Why: Screen-reader users navigate by headings; a skipped level suggests missing content and breaks the outline.
Fix: Use consecutive levels (h2 -> h3), and style headings with CSS instead of choosing levels by size.

### SEO-07 Missing canonical link
Severity: medium
Detection: no `<link>` whose `rel` contains the token `canonical` and whose `href` is not empty.
Findings: one per page; element: the `<head>` start tag.
Why: Landing pages are often reached through many tracking URLs. Without a canonical, search engines may index duplicates and split ranking signals.
Fix: Add `<link rel="canonical" href="<clean page URL>">`.

### SEO-08 hreflang without x-default
Severity: low
Detection: at least one `<link>` whose `rel` contains the token `alternate` and that has an `hreflang` attribute exists, and none of them has `hreflang="x-default"`.
Findings: one per page; element: the `<head>` start tag.
Why: Multi-language pages need a fallback for users whose language is not listed.
Fix: Add `<link rel="alternate" hreflang="x-default" href="<default URL>">`.

### SEO-09 Missing Open Graph tags
Severity: low
Detection: `<meta property="og:title">` or `<meta property="og:image">` is missing or has empty `content`.
Findings: one per page, the detail lists which of the two is missing; element: the `<head>` start tag.
Why: Landing pages are shared in social apps and messengers. Without Open Graph the preview has no image and a random title.
Fix: Add the tags named in the finding: `og:title` with the offer, and `og:image` at 1200x630.

## Accessibility

### A11Y-01 Missing page language
Severity: high
Detection: `<html>` has no `lang` attribute or it is empty after trimming.
Findings: one per page; element: the `<html ...>` start tag.
Why: Screen readers choose pronunciation by the page language. Without it Hebrew text may be read with English rules.
Fix: Add `lang` to `<html>`, for example `lang="he"` or `lang="en"`.

### A11Y-02 Image without alt attribute
Severity: high
Detection: an `<img>` without an `alt` attribute. (`alt=""` is valid for decorative images and is not reported.)
Findings: one per image; element: the `<img>`.
Why: Screen readers read the file name instead, and the image content is lost for blind users and for search.
Fix: Add `alt` that describes the image's purpose, or `alt=""` if it is decorative.

### A11Y-03 Link without accessible name
Severity: high
Detection: an `<a>` with an `href` attribute that has no accessible name.
Findings: one per link; element: the `<a>`.
Why: Screen readers announce only "link", so users cannot know where it leads. Common with icon-only links.
Fix: Add visible text, or `aria-label` describing the destination, or `alt` on the image inside.

### A11Y-04 Button without accessible name
Severity: high
Detection: a `<button>` or an element with `role="button"` that has no accessible name.
Findings: one per button; element: the button.
Why: Icon-only buttons are announced as "button" with no purpose, so the call to action is unusable without sight.
Fix: Add `aria-label`, or visually hidden text inside the button.

### A11Y-05 Form field without label
Severity: high
Detection: an `<input>` (except `type` hidden, submit, button, reset, image; an `<input>` without `type` counts as text), `<select>` or `<textarea>` that has no non-empty `aria-label`, no `aria-labelledby`, is not inside a `<label>`, and has no `<label for>` matching its `id`. A `placeholder` alone does not count.
Findings: one per field; element: the field.
Why: Lead forms are the core of a landing page. Without labels, screen-reader users do not know what to type, and the placeholder disappears when typing starts.
Fix: Add a `<label for="<id>">` for each field.

### A11Y-06 Zoom disabled
Severity: high
Detection: split the `content` of `<meta name="viewport">` on commas into `key=value` pairs, trimming spaces around keys and values. Report if `user-scalable` is `no` or `0`, or if `maximum-scale` is a number below 2. A `maximum-scale` value that is not a number is ignored.
Findings: one per page; element: the `<meta name="viewport">` element.
Why: Users with low vision cannot zoom on mobile. This fails WCAG 1.4.4.
Fix: Remove `user-scalable` and `maximum-scale`; use `width=device-width, initial-scale=1`.

### A11Y-07 Positive tabindex
Severity: medium
Detection: any element whose `tabindex` is an integer greater than 0. Values that are not integers are ignored.
Findings: one per element; element: that element.
Why: It forces a custom tab order that rarely matches the visual order and confuses keyboard users.
Fix: Use `tabindex="0"` or none, and order the DOM to match the visual order.

### A11Y-08 Generic link text
Severity: low
Detection: an `<a>` without a non-empty `aria-label` whose text, after removing punctuation at both ends, equals one of: "click here", "here", "read more", "more", "learn more", "לחצו כאן", "לחץ כאן", "כאן", "קרא עוד", "קראו עוד", "למידע נוסף".
Findings: one per link; element: the `<a>`.
Why: Screen-reader users often list all links on a page; many "click here" links are meaningless out of context.
Fix: Write link text that names the destination, for example "Open a demo account".

### A11Y-09 Duplicate id
Severity: medium
Detection: the same non-empty `id` value (compared exactly, case-sensitive) on more than one element.
Findings: one per duplicated value, the detail states how many elements share it; element: the second element with that id.
Why: Labels, `aria-labelledby` and in-page links point to the first match only, so forms and navigation break.
Fix: Make every `id` unique.

## Performance

### PERF-01 Image without dimensions
Severity: medium
Detection: an `<img>` missing a `width` or a `height` attribute, or with either one empty.
Findings: one per image; element: the `<img>`.
Why: The browser cannot reserve space before the image loads, so content jumps (Cumulative Layout Shift), which hurts Core Web Vitals and conversions.
Fix: Add `width` and `height` with the image's intrinsic size; control display size with CSS.

### PERF-02 Image not lazy-loaded
Severity: low
Detection: the third `<img>` in document order and every one after it, when it does not have `loading="lazy"`.
Findings: one per image; element: the `<img>`.
Why: Images far down the page are downloaded before the user scrolls, competing with the hero image.
Fix: Add `loading="lazy"` to images below the first screen.

### PERF-03 Render-blocking script in head
Severity: medium
Detection: a `<script>` with a `src` attribute inside `<head>` that has no `defer` attribute, no `async` attribute, and no `type="module"`.
Findings: one per script; element: the `<script>`.
Why: The browser stops rendering until the script downloads and runs, delaying the first paint.
Fix: Add `defer`, or move the script to the end of `<body>`.

### PERF-04 First image lazy-loaded
Severity: medium
Detection: the first `<img>` in document order has `loading="lazy"`.
Findings: one per page; element: that `<img>`.
Why: The first image is usually the hero and the Largest Contentful Paint element. Lazy-loading it delays LCP.
Fix: Remove `loading="lazy"` from the hero image; consider `fetchpriority="high"`.

## Internationalization

### I18N-01 RTL language without dir
Severity: high
Detection: the primary subtag of `<html lang>` (the part before the first `-`) is one of `he`, `iw`, `ar`, `fa`, `ur`, `yi`, and `<html>` does not have `dir="rtl"`.
Findings: one per page; element: the `<html ...>` start tag.
Why: Without `dir="rtl"` punctuation, numbers and mixed Hebrew-English text are shown in the wrong order, and layout mirrors fail.
Fix: Add `dir="rtl"` to `<html>`.

## Security

### SEC-01 New-tab link without noopener
Severity: low
Detection: an `<a target="_blank">` whose `rel` contains neither the token `noopener` nor the token `noreferrer`.
Findings: one per link; element: the `<a>`.
Why: The opened page can access `window.opener` and redirect the landing page (reverse tabnabbing).
Fix: Add `rel="noopener noreferrer"`.

### SEC-INJ Hidden instructions for AI
Severity: high
Detection: by the `content_guard` node (LLM), not by `run_checks`.
Findings: one per page, the detail quotes the hidden text; element: the element that contains it.
Why: Text aimed at AI tools can manipulate automated reviews or assistants that read the page.
Fix: Remove the text, and check who added it to the page.
