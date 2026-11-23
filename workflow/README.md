# workflow/

This is the code behind the AutoSE workflow. GitHub runs the files in `.github/`; the folder
`github/` here is an exact copy of them, as the assignment asks (a test checks the copy is up to
date).

## Files

| File | What it does |
| :--- | :--- |
| `autose/intake.py` | Decides whether an event should start a run: right label or command, a maintainer, review rounds left. Maps a `/autose` on a PR back to its issue. |
| `autose/plan.py` | Planner agent. Stage 1 writes `spec.md`, Stage 2 writes `design.md`. Read-only tools. |
| `autose/build.py` | Builder agent. Stages 3 and 4, with the retry loop: up to 3 attempts, then one design revision, then one more cycle. |
| `autose/release.py` | Stage 5. A plain script: applies the patch on `autose/issue-N`, pushes, opens or updates the PR. |
| `autose/ci.py` | Stage 5 check. Runs the tests and mypy on the PR head and posts an `autose/ci` status. |
| `autose/review.py` | Reviewer agent. Stage 6, in its own read-only job. Posts a comment review. |
| `autose/finalize.py` | Records how many review rounds are used and comments on the issue. |
| `autose/gates.py` | The check for every stage. Plain code makes the pass/fail decision. |
| `autose/tools.py` | The tools each agent gets, and the rules on what it can touch. |
| `autose/llm.py` | The agent loop on the Anthropic Messages API. |
| `autose/budget.py` | Token and cost tracking with hard caps. |
| `autose/github.py` | `gh` helpers and the status comment that stores run state. |
| `prompts/` | One prompt per agent. `planner_spec.md` is based on my A1 requirements skill. |
| `tests/` | Tests for the harness that run without a model or GitHub. |

Repository-specific settings (test command, allowed paths, models, budgets) are in `.autose.yml`
at the repo root.

## Running the tests

```
python -m pip install anthropic pyyaml pytest
python -m pytest -o addopts= workflow/tests
```
