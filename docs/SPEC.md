# LP Auditor Agent - Specification

## 1. Purpose

A focused agent, not a general chat. The user gives a path to a local landing-page HTML file. The agent finds SEO, accessibility, basic performance, i18n and link-safety issues, explains each one and suggests a fix, and saves a Markdown report after the user approves.

Out of scope: anything that is not auditing a landing page. The agent refuses politely with a fixed reply that says what it does.

Target audience: frontend developers, marketing web teams, landing-page owners.

## 2. Stack

- LangGraph for the workflow, LangSmith for tracing, OpenRouter as the only LLM provider.
- BeautifulSoup4 (`html.parser`, no lxml) for HTML checks.
- `rank-bm25` for retrieval over `agent/knowledge/rules.md`. No embeddings.
- `rich` + `prompt_toolkit` for the CLI.
- PyInstaller, one-file console build: `dist/agent.exe`.

## 3. Folder tree

```
lp-auditor/
├── agent/
│   ├── __init__.py
│   ├── graph.py          # LangGraph workflow
│   ├── nodes.py          # guards, report writer, evaluator, HITL
│   ├── tools.py          # load_page, run_checks, BM25 retrieval, cost helpers
│   ├── cli.py            # CLI entrypoint
│   ├── models.yaml       # model ids per role and profile
│   └── knowledge/
│       └── rules.md      # rule base for RAG (given)
├── evals/
│   ├── compare_models.py
│   ├── cost_eval.py
│   ├── scope_eval.py
│   ├── rubric.md
│   ├── fixtures/         # sample pages, expected.json, scope_questions.json (given)
│   └── results/          # CSV outputs
├── tests/
├── scripts/build.ps1
├── docs/SPEC.md, docs/PROMPTS.md
├── manifest.json
├── requirements.txt
├── README.md
├── .env.example
└── .gitignore
```

## 4. Graph

State (TypedDict): `user_message`, `page_path`, `html`, `page_text`, `in_scope`, `injection_in_message`, `injection_in_page`, `findings` (list), `rules` (list of retrieved rule chunks), `report`, `eval_passed`, `eval_feedback`, `revision_count`, `save_approved`, `saved_path`, `usage` (list of per-call records), `error`.

| Node | LLM? | Does | Next |
| --- | --- | --- | --- |
| `input_guard` | yes, `guard` role | Classifies the user message: in scope (asks to audit / explain an audit of a landing page) or not; detects prompt-injection attempts. Structured output `{in_scope, injection, reason}`. | in scope and no injection -> `load_page`; else -> `refuse` |
| `refuse` | no | Fixed English reply: what the agent does + an example command. If injection, says the request was blocked. | END |
| `load_page` | no | Extracts the path from the message (or from `audit <path>`). Validates: exists, `.html`/`.htm`, size <= 2 MB, UTF-8 (fallback cp1255/latin-1). Clear error otherwise. | `content_guard` or END on error |
| `content_guard` | yes, `guard` role | Looks at visible and hidden page text (including `display:none` elements and HTML comments) for instructions aimed at an AI. Never follows them. Sets `injection_in_page` and adds a `SEC-INJ` finding with the quoted text. | `run_checks` |
| `run_checks` | no | Runs every rule in `rules.md` that has a Detection line, exactly as written there. Each finding: `{rule_id, severity, element (short HTML snippet <= 200 chars), detail}`. | `retrieve_rules` |
| `retrieve_rules` | no | BM25 index over `rules.md` split by `### ` headings. For each distinct `rule_id` in findings, takes that rule's chunk by id; plus top-3 BM25 chunks for the user's free text. | `write_report` |
| `write_report` | yes, `writer` role | Writes the report (format below) only from `findings` + `rules`. If `eval_feedback` exists, fixes exactly those points. | `evaluator` |
| `evaluator` | yes, `evaluator` role (different model family from writer) | Checks: every issue in the report maps to a finding; no finding is missing; no invented issues; format kept. Structured output `{passed, feedback}`. | passed -> `confirm_save`; failed and `revision_count < 1` -> `write_report`; else -> `confirm_save` with a warning line added to the report |
| `confirm_save` | no | Prints the report and asks via `interrupt()`: `Save report to <path>? [Y/N]`. | Y -> `save_report`; N -> END |
| `save_report` | no | Writes `<page_name>.report.md` next to the audited file. | END |

### Report format

```
# Landing Page Audit: <file name>
Score: <passed checks>/<total checks> | Issues: <n> (high <h>, medium <m>, low <l>)

## Summary
<2-3 sentences: the most important problems and their effect on users/search>

## Issues
### [<severity>] <rule_id> - <rule title>
- Where: `<element snippet>`
- Why it matters: <from the rule>
- Fix: <concrete, using the element>

## Security notes
<only if SEC-INJ: quote the hidden instruction and say it was ignored>
```

Severities come from `rules.md`. Issues are ordered high -> low.

## 5. Models

`agent/models.yaml`: for each role (`guard`, `writer`, `evaluator`, `judge`) and each profile (`free`, `paid`), a list of 2-3 OpenRouter model ids. At startup the agent calls `GET https://openrouter.ai/api/v1/models` once and uses the first listed id that is available. If none is available: a clear error, not a crash.

- `free` profile: models whose id ends with `:free`. `writer` and `evaluator` must be from different model families.
- `paid` profile: cheap models (for example a Gemini Flash class model). Used only in evals.
- `judge` (evals only): one fixed paid model, never the same as the writer under test.
- On HTTP 429 or a model error: try the next model in the role list, print `[WARN] Switching model: <a> -> <b>`.
- Every structured-output call gets one retry on invalid JSON before switching model.

## 6. Cost tracking

- Every LLM call records `{node, model, prompt_tokens, completion_tokens, cost_usd}`. Use OpenRouter usage accounting (`usage: {include: true}`) to get `cost`.
- For `:free` models also compute `theoretical_cost_usd` from the pricing of the paired paid model in `models.yaml` (`theoretical_price_from`), taken from the models endpoint.
- After each task print: `[COST] total $<x> (theoretical $<y>) | tokens in <a> / out <b> | calls <n>`.
- `MAX_COST_USD` (default 0.50) per task: if the next call would exceed it, stop and tell the user.

## 7. CLI

Start: `agent.exe` or `python -m agent.cli`. Key from `.env` next to the exe; if missing, hidden prompt (`getpass`). LangSmith key optional: without it, one line `[INFO] LangSmith tracing is off`.

| Command | Does |
| --- | --- |
| `help`, `?` | Short guide: what the agent does, commands, an example |
| `audit <path>` or a message containing a path | Runs the graph |
| `/cost` | Cost and tokens so far this session, by node and model |
| `/models` | Active model per role and profile |
| `/new` | Clears session state |
| `/summary` | Bonus: writes the session summary to a local `.txt` after `[Y/N]` |
| `/quit` | Exit |

Streaming: `graph.stream(..., stream_mode="updates")`; every node prints `[INFO] Entering Node: <name>`.

Errors: one line `[ERROR] <what happened> - <what to do>`. Dedicated messages for: missing/invalid key (401), no credit (402), rate limit (429), no network, file not found, not HTML, file too big. Traceback only with `--debug` and in `agent.log`.

`--auto` flag: runs one audit non-interactively (`--auto <path> --yes|--no`), used by the evals.

## 8. Evals

All results are CSV files in `evals/results/`. Fixtures in `evals/fixtures/` (given): three pages and `expected.json` with the expected rule ids per page.

1. `compare_models.py`: run the audit of all three fixture pages with 3 writer models (2 free + 1 paid). Columns: `model, page, seconds, cost_usd, theoretical_cost_usd, recall (expected rule ids found in report), precision (report rule ids that are expected), judge_relevance, judge_accuracy, judge_completeness, judge_format, judge_avg`. The judge model is fixed for all rows and scores 1-5 by `evals/rubric.md`.
2. `cost_eval.py`: 3 common tasks (the 3 fixture pages), one free and one paid profile. Columns: `profile, page, node, model, tokens_in, tokens_out, cost_usd, theoretical_cost_usd`, plus a total row per task.
3. `scope_eval.py`: all questions in `evals/fixtures/scope_questions.json`. Columns: `id, question, expected, actual, correct`. Last row: refusal rate on out-of-scope questions and pass rate on in-scope questions.

## 9. Delivery

- `scripts/build.ps1`: PyInstaller one-file console build, includes `agent/knowledge/rules.md` and `agent/models.yaml` as data files.
- GitHub Release `v1.0.0` with `agent.exe`. `manifest.json` `download_url` points to it.
- README: what the agent does, graph diagram (Mermaid), extensions (RAG), install and run (source and exe), CLI commands, evals with latest results table, required keys, sample report.
- `.env.example`: `OPENROUTER_API_KEY`, `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`, `LANGSMITH_PROJECT`, `MAX_COST_USD`, `PROFILE` - names only.

## 10. Day plan

Each day ends with: tests pass, `ruff` clean, exe builds, commit + push.

| Day | Date | Task | Done when |
| --- | --- | --- | --- |
| 1 | Thu 19.11 | Scaffold, requirements, `.env.example`, `.gitignore`, `models.yaml` with startup availability check, OpenRouter client with cost record, CLI REPL with `help`/`?`/`/quit` | `python -m agent.cli` starts, `help` works, a test question returns an answer and a `[COST]` line |
| 2 | Fri 20.11 | Skeleton graph (`input_guard` -> `refuse` / echo), `[INFO]` streaming, LangSmith, `scripts/build.ps1`, first exe | `agent.exe` runs from another folder; the run appears in LangSmith |
| 3 | Sun 22.11 | `load_page`, `run_checks` for every rule with a Detection line | For each fixture page, `run_checks` returns exactly the ids in `expected.json` except `SEC-INJ` (that one comes from `content_guard` on day 5); pytest covers it |
| 4 | Mon 23.11 | `retrieve_rules` (BM25), `write_report` | A full report is printed for a fixture page; every issue cites a rule id |
| 5 | Tue 24.11 | `content_guard`, `evaluator` with one revision loop, `confirm_save` with `interrupt()`, `save_report` | End-to-end run: stops at `[Y/N]`, saves the report; out-of-scope question is refused; hidden instruction in the a11y fixture is reported, not followed |
| 6 | Wed 25.11 | `/cost`, `/models`, `/new`, central error handling, key prompt, model fallback on 429/402, `--debug`, `--auto` | All commands work inside the exe; wrong path and wrong key give a clear one-line error |
| 7 | Thu 26.11 | `rubric.md`, judge, the three evals, first run on the paid profile | Three CSV files in `evals/results/` |
| 8 | Fri 27.11 | README, `manifest.json`, final build, Release `v1.0.0` | Download from Releases and run works |
| 9 | Sun 29.11 | Checklist pass, clean-machine test (no Python), `/summary` if time allows | Every row of the course checklist is checked |

If time runs short, drop `/summary` first, then `/models`. Never drop days 7-8.
