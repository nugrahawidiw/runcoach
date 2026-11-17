# Moving development to Claude Code

Claude Code works inside your project folder and can read files, run commands and edit code (asking your
permission). It does **not** remember the chat this project came from. Everything it needs is written down in
`CLAUDE.md` (read automatically at the start of every session) and the files in `docs/`.

## 1. Install Claude Code
Follow the official Claude Code documentation for the current Windows instructions. Methods have changed over time
(a native installer, WinGet, or npm; on Windows some setups need Git for Windows or WSL), so do not rely on old
blog posts. Check it works with `claude --version` in a new Command Prompt.

## 2. Prepare the project (one time)
In the project folder (the one containing `pyproject.toml`, quote paths that contain spaces):
```
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest
```
Expect `34 passed`. Then create your own `.env` (copy `.env.example`) and, optionally, `profile.toml`.

Start version control so every Claude Code change can be reviewed and undone:
```
git init
git add .
git status
git commit -m "Initial runcoach project"
```
Check that `git status` does **not** list `.env`, `data/` or `reference/` before committing.
If you do not have Git yet, install Git for Windows first.

## 3. Start a session
```
cd "D:\path\to\runcoach"
claude
```
Claude Code loads `CLAUDE.md`. You can check what it knows by asking: "Summarize this project and what is verified."

## 4. Suggested first prompts (in this order)
1. **Orient:** "Read CLAUDE.md and docs/ARCHITECTURE.md, run the tests, and explain the project in 10 lines."
2. **Live Strava test:** "Walk me through `runcoach auth` and `sync --days 7` step by step. If Strava's real responses differ
   from what the code assumes, fix the code and add a sanitized recorded-response test. Do not print any secrets."
3. **Compare with known numbers:** "Run `analyze` on my Oct 11 long run and check it against the golden numbers in
   docs/COACHING_CONTEXT.md."
4. **Garmin run file:** "I exported a run from Garmin Connect. Run `fit-analyze` on it, compare with Strava, and fix any
   mismatch. See docs/FIT_AND_WELLNESS_NOTES.md section 5."
5. **Sleep stages:** "Compare the stage minutes with what Garmin Connect shows for one night I will give you, and
   fix `stage_minutes` if it is wrong."
6. **Tooling:** "Add ruff and a pre-commit hook, and explain each change in plain language."
Then pick items from `docs/ROADMAP.md` (P1) one at a time.

## 5. Working agreements that avoid trouble
- Ask Claude Code to **propose a plan and wait for your OK** before large changes or new dependencies.
- Ask it to explain every command it wants to run, in plain words, and approve them one by one at first.
- Commit after each working step (`git commit`) so you can go back.
- Tests must stay green; ask for a test with every change. Formulas are pinned to real session numbers.
- Never paste secrets into a prompt. If a secret leaks, rotate it on Strava's API page.
- Keep private data out of the repository. Before turning real data into a fixture, strip names, locations and
  anything you would not post publicly.
- Keep docs current: `python scripts/gen_api_docs.py` after signature changes, and edit `docs/*.md` when behaviour
  or assumptions change. Say "update the docs" at the end of a task.

## 6. Reference files from the chat
Copy these into a folder named `reference/` (already git-ignored) if you want Claude Code to replicate them later:
the dashboard HTML (its `STREAMS` entries show the chart design), the training plan markdown, the calendar `.ics`,
and the story-pack documentation. They contain personal training data, so keep them out of any public repository.

## 7. What carries over and what does not
Carries over: all code, tests, docs, the coaching rules in `docs/COACHING_CONTEXT.md`.
Does not carry over: the chat's memory, the Strava connector used to read your data here, and the hand-built
dashboard generator. Those are the P1/P2 roadmap items.
