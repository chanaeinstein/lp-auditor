# Prompts for Claude Code

## 1. Kickoff prompt (day 1, once, in the cloned repo)

Before running: the repo `lp-auditor` exists on GitHub (public), it is cloned, `gh auth login` is done, and the starter files are unzipped in the repo folder.

```text
You are setting up a new project. Read CLAUDE.md and docs/SPEC.md fully before doing anything. Explain to me in Hebrew; write code and files in English.

Do these steps in order and stop after step 6 with a short report in Hebrew.

1. Scaffold the repository exactly as the folder tree in docs/SPEC.md section 3. Keep the given files (agent/knowledge/rules.md, evals/fixtures/*, manifest.json, docs/*). Files that belong to later days contain only a docstring saying which day implements them.
2. requirements.txt: langgraph, langchain-openai (pointed at the OpenRouter base URL), langsmith, beautifulsoup4, rank-bm25, rich, prompt_toolkit, pydantic, pyyaml, python-dotenv, httpx, pytest, ruff, pyinstaller. Create a venv and install. Pin the versions that were installed.
3. .env.example with the names in docs/SPEC.md section 9, no values. .gitignore must include .env, venv, .venv, dist, build, __pycache__, *.log, *.report.md.
4. Ask me to create .env with my keys myself. Wait until I say it is done. Never print the keys.
5. Implement day 1 from docs/SPEC.md section 10: models.yaml with the startup availability check, the OpenRouter client that records cost per call, and a CLI REPL with help, ? and /quit that sends a free-text question to the guard model and prints the answer and a [COST] line. Add pytest tests with a mocked LLM.
6. Run ruff and pytest, then commit "feat: day 1 - scaffold, OpenRouter client, CLI" and push to main.
```

## 2. Daily prompt (start of every evening, from day 2)

```text
git pull. Read CLAUDE.md and docs/SPEC.md. Today is day <N> in docs/SPEC.md section 10.
Give me a plan in Hebrew of at most 8 lines for today's task and its "Done when" criterion, and wait for my OK.
After my OK: implement with unit tests (mock the LLM), run ruff and pytest, and run scripts/build.ps1.
Then show me how to check the "Done when" criterion myself, step by step, in Hebrew.
```

## 3. End-of-evening check

```text
Check today's work against docs/SPEC.md section 10, day <N>, and against the hard requirements in CLAUDE.md:
[INFO] line in every node, OpenRouter only, interrupt() before writing files, folder tree unchanged, no key or .env committed, exe builds.
List blocking problems first, then small notes. Fix blocking problems, run the tests again, then commit "feat: day <N> - <short summary>" and push.
```
