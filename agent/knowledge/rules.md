# Landing Page Audit Rules

DRAFT - to be reviewed by the project owner before day 4.

Each rule has: Severity, Detection (implemented in plain Python in `run_checks`, exactly as written), Why, Fix. Text matching is case-insensitive and trims whitespace. "Accessible name" means: non-empty visible text, or a non-empty `aria-label`, or `aria-labelledby` pointing to an element with text, or (for links/buttons containing an image) an `img` with non-empty `alt`.

## SEO

### SEO-01 Missing page title
Severity: high
Detection: no `<title>` in `<head>`, or its text is empty.
Why: The title is the main line shown in search results and browser tabs. Without it search engines invent one and click-through drops.
Fix: Add a unique `<title>` that states the offer, 30-60 characters.

### SEO-02 Title length out of range
Severity: low
Detection: `<title>` text exists and its length is below 30 or above 60 characters.
Why: Short titles waste the space in search results; long ones are cut off, often in the middle of the offer.
Fix: Rewrite the title to 30-60 characters, with the main keyword near the start.

### SEO-03 Missing meta description
Severity: medium
Detection: no `<meta name="description">`, or its `content` is empty.
Why: Search engines use it as the snippet under the title. Without it they take random page text.
Fix: Add a `<meta name="description">` of 70-160 characters that summarizes the offer and the call to action.

### SEO-04 Meta description length out of range
Severity: low
Detection: meta description exists and its `content` length is below 70 or above 160 characters.
Why: Too short gives users no reason to click; too long is cut off.
Fix: Rewrite it to 70-160 characters.

### SEO-05 Not exactly one H1
Severity: medium
Detection: the number of `<h1>` elements is not 1.
Why: One H1 tells search engines and screen-reader users what the page is about. Zero or several H1s blur the main topic.
Fix: Keep a single H1 with the main message; turn the others into H2.

### SEO-06 Skipped heading level
Severity: low
Detection: walking all `h1`-`h6` in document order, a heading's level is more than one deeper than the previous heading's level (for example `h2` followed by `h4`). Report each jump once.
Why: Screen-reader users navigate by headings; a skipped level suggests missing content and breaks the outline.
Fix: Use consecutive levels (h2 -> h3), and style headings with CSS instead of choosing levels by size.

### SEO-07 Missing canonical link
Severity: medium
Detection: no `<link rel="canonical">` with a non-empty `href`.
Why: Landing pages are often reached through many tracking URLs. Without a canonical, search engines may index duplicates and split ranking signals.
Fix: Add `<link rel="canonical" href="<clean page URL>">`.

### SEO-08 hreflang without x-default
Severity: low
Detection: at least one `<link rel="alternate" hreflang="...">` exists and none has `hreflang="x-default"`.
Why: Multi-language pages need a fallback for users whose language is not listed.
Fix: Add `<link rel="alternate" hreflang="x-default" href="<default URL>">`.

### SEO-09 Missing Open Graph tags
Severity: low
Detection: `<meta property="og:title">` or `<meta property="og:image">` is missing or has empty `content`. One finding listing what is missing.
Why: Landing pages are shared in social apps and messengers. Without Open Graph the preview has no image and a random title.
Fix: Add `og:title`, `og:description`, `og:image` (1200x630) and `og:url`.

## Accessibility

### A11Y-01 Missing page language
Severity: high
Detection: `<html>` has no `lang` attribute or it is empty.
Why: Screen readers choose pronunciation by the page language. Without it Hebrew text may be read with English rules.
Fix: Add `lang` to `<html>`, for example `lang="he"` or `lang="en"`.

### A11Y-02 Image without alt attribute
Severity: high
Detection: an `<img>` without an `alt` attribute. (`alt=""` is valid for decorative images and is not reported.)
Why: Screen readers read the file name instead, and the image content is lost for blind users and for search.
Fix: Add `alt` that describes the image's purpose, or `alt=""` if it is decorative.

### A11Y-03 Link without accessible name
Severity: high
Detection: an `<a href>` without an accessible name.
Why: Screen readers announce only "link", so users cannot know where it leads. Common with icon-only links.
Fix: Add visible text, or `aria-label` describing the destination, or `alt` on the image inside.

### A11Y-04 Button without accessible name
Severity: high
Detection: a `<button>` or an element with `role="button"` without an accessible name.
Why: Icon-only buttons are announced as "button" with no purpose, so the call to action is unusable without sight.
Fix: Add `aria-label`, or visually hidden text inside the button.

### A11Y-05 Form field without label
Severity: high
Detection: an `<input>` (except `type` hidden, submit, button, reset, image), `<select>` or `<textarea>` that has no `aria-label`, no `aria-labelledby`, is not inside a `<label>`, and has no `<label for>` matching its `id`. A `placeholder` alone does not count.
Why: Lead forms are the core of a landing page. Without labels, screen-reader users do not know what to type, and the placeholder disappears when typing starts.
Fix: Add a `<label for="<id>">` for each field.

### A11Y-06 Zoom disabled
Severity: high
Detection: `<meta name="viewport">` content contains `user-scalable=no` or `user-scalable=0`, or `maximum-scale` below 2.
Why: Users with low vision cannot zoom on mobile. This fails WCAG 1.4.4.
Fix: Remove `user-scalable` and `maximum-scale`; use `width=device-width, initial-scale=1`.

### A11Y-07 Positive tabindex
Severity: medium
Detection: any element with `tabindex` greater than 0.
Why: It forces a custom tab order that rarely matches the visual order and confuses keyboard users.
Fix: Use `tabindex="0"` or none, and order the DOM to match the visual order.

### A11Y-08 Generic link text
Severity: low
Detection: a link whose whole text is one of: "click here", "here", "read more", "more", "learn more", "לחצו כאן", "לחץ כאן", "כאן", "קרא עוד", "קראו עוד", "למידע נוסף".
Why: Screen-reader users often list all links on a page; many "click here" links are meaningless out of context.
Fix: Write link text that names the destination, for example "Open a demo account".

### A11Y-09 Duplicate id
Severity: medium
Detection: the same `id` value on more than one element. One finding per duplicated value.
Why: Labels, `aria-labelledby` and in-page links point to the first match only, so forms and navigation break.
Fix: Make every `id` unique.

## Performance

### PERF-01 Image without dimensions
Severity: medium
Detection: an `<img>` missing a `width` or a `height` attribute.
Why: The browser cannot reserve space before the image loads, so content jumps (Cumulative Layout Shift), which hurts Core Web Vitals and conversions.
Fix: Add `width` and `height` with the image's intrinsic size; control display size with CSS.

### PERF-02 Image not lazy-loaded
Severity: low
Detection: the third `<img>` in document order and every one after it, when it has no `loading="lazy"`.
Why: Images far down the page are downloaded before the user scrolls, competing with the hero image.
Fix: Add `loading="lazy"` to images below the first screen.

### PERF-03 Render-blocking script in head
Severity: medium
Detection: a `<script src>` inside `<head>` without `defer`, without `async`, and without `type="module"`.
Why: The browser stops rendering until the script downloads and runs, delaying the first paint.
Fix: Add `defer`, or move the script to the end of `<body>`.

### PERF-04 First image lazy-loaded
Severity: medium
Detection: the first `<img>` in document order has `loading="lazy"`.
Why: The first image is usually the hero and the Largest Contentful Paint element. Lazy-loading it delays LCP.
Fix: Remove `loading="lazy"` from the hero image; consider `fetchpriority="high"`.

## Internationalization

### I18N-01 RTL language without dir
Severity: high
Detection: `<html lang>` starts with `he`, `ar`, `fa` or `yi`, and `<html>` has no `dir="rtl"`.
Why: Without `dir="rtl"` punctuation, numbers and mixed Hebrew-English text are shown in the wrong order, and layout mirrors fail.
Fix: Add `dir="rtl"` to `<html>`.

## Security

### SEC-01 New-tab link without noopener
Severity: low
Detection: an `<a target="_blank">` whose `rel` does not contain `noopener` or `noreferrer`.
Why: The opened page can access `window.opener` and redirect the landing page (reverse tabnabbing).
Fix: Add `rel="noopener noreferrer"`.

### SEC-INJ Hidden instructions for AI
Severity: high
Detection: by the `content_guard` node (LLM), not by `run_checks`.
Why: Text aimed at AI tools can manipulate automated reviews or assistants that read the page.
Fix: Remove the text, and check who added it to the page.
