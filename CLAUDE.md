# LP Auditor Agent - project rules for Claude Code

Final project for an LLM-systems course. A CLI agent (LangGraph + OpenRouter + LangSmith) that audits a landing-page HTML file for SEO, accessibility and basic performance issues and writes a fix report. The full spec is `docs/SPEC.md` - read the relevant section before every task. The day-by-day plan is in `docs/SPEC.md`, section "Day plan".

## Hard requirements (graded)
- Folder tree must stay exactly as in `docs/SPEC.md`: `agent/{__init__,graph,nodes,tools,cli}.py`, `evals/{compare_models,cost_eval,scope_eval}.py`, `evals/rubric.md`, `evals/results/`, `manifest.json`, `requirements.txt`, `README.md`, `.env.example`. Extra files go inside these folders.
- Every LLM call goes through OpenRouter. No direct provider SDKs.
- Every node prints `[INFO] Entering Node: <name>` when it starts.
- Writing any file to disk stops the graph with `interrupt()` and asks `[Y/N]`.
- The app must keep building into a single `agent.exe` with PyInstaller. Run the build at the end of every working day.
- Never commit `.env` or any key.

## Working rules
- One developer. Commit at the end of each day with a clear message (`feat: day 3 - load_page and run_checks`). Push to `main`.
- Before starting: `git pull`, read `docs/SPEC.md`.
- Give a plan of at most 8 lines and wait for OK before writing code.
- Explain plans and results to the user in Hebrew. Code, comments, commit messages and everything the end user sees in the CLI and in the report are English.

## Cost rules
- Default profile is `free`. A paid model is used only in the evals (day 7).
- Unit tests never call a real model - mock the LLM.
- Respect `MAX_COST_USD`.

## Code style
- Python 3.12, type hints, `ruff` clean, `pytest` for every new module.
- Deterministic logic (HTML checks, rule retrieval, file IO) is plain Python, never an LLM call.
- Prompts to the models are written as a principle with its reason, not as a list of cases.
- Model ids live only in `agent/models.yaml`.
- No heavy dependencies (no torch, no embeddings libraries). The exe must stay small.
