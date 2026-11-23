# AutoSE Assignment 3: from issue to pull request

Roll no: 2025204015

This is a fork of [TinyDB](https://github.com/msiemens/tinydb) that I use for Assignment 3. The idea
is simple: a maintainer labels an issue, and a set of agents turns it into a pull request that has
been tested and reviewed. The agents write a spec, plan the change, edit the code, run the tests,
open the PR, and then a separate reviewer agent checks it. The bot never merges anything. A person
looks at the PR and decides.

The original TinyDB readme is still here as [README.rst](README.rst).

## Base commit

The fork is pinned to upstream commit `edff96aeb2616402e9489d46e90a592c05565621` (tagged
`autose-base`). It's the same commit I used in A2, so I can reuse the `ARCHITECTURE.md` I wrote
there.

## How it works

The workflow goes through six stages. Each one saves a file, and the next stage only starts if a
check on that file passes.

| Stage | Who does it | Output | Check |
| :--- | :--- | :--- | :--- |
| 1. Requirements | Planner agent | `spec.md` | every acceptance criterion can be tested |
| 2. Design | Planner agent | `design.md` | the files and functions it names really exist |
| 3. Implementation | Builder agent | `diff.patch` | the code builds |
| 4. Testing | Builder agent | `test_report.md` | old and new tests all pass |
| 5. Release | script, no model | `pr.md` + PR link | the PR is open and CI passes |
| 6. Review | Reviewer agent | `review.md` | the reviewer approves, or two rounds are used up |

If tests keep failing, the builder retries a few times, and after that the planner gets one chance
to change the design. If the reviewer asks for changes, the work goes back to the builder (for code
problems) or the planner (for a wrong approach), at most twice.

The reviewer runs in its own job with read-only access. It only sees the issue, the diff and the
code. It never sees the spec, the plan or anything the other agents said, so it can't just agree
with them.

The reasons behind these choices are in the ADRs in [architecture/decisions](architecture/decisions),
and there's a diagram in [architecture/views](architecture/views).

## Models

| Role | Model |
| :--- | :--- |
| Planner (stages 1–2) | Claude Sonnet 5.5 |
| Spec testability check | Claude Haiku 5.5 |
| Builder (stages 3–4) | Claude Sonnet 5.5 |
| Release and CI (stage 5) | none, it's a plain script |
| Reviewer (stage 6) | GPT-5, or Claude Opus 5.5 if there's no OpenAI key |

## Running it

On any issue in this repo, a maintainer either adds the label `autose` or writes a comment starting
with `/autose`. Labels and comments from other people are ignored. If two runs start for the same
issue, the second one waits for the first.

To set it up in your own fork you need to:

1. Turn on Issues in the repo settings.
2. In Settings → Actions → General, allow GitHub Actions to create pull requests.
3. Add `ANTHROPIC_API_KEY` (and `OPENAI_API_KEY` if you want the GPT reviewer) as repository secrets.
4. Set a spending limit with your model provider before the first run.

## What's in this repo

- `architecture/decisions/` – the ADRs, one per design decision
- `architecture/views/` – component view, stage map, and later the sequence view of a real run
- `workflow/` – the workflow files, agent code and prompts (in progress)
- `experiment/issues/` – the five issues I opened to test the workflow
- `experiment/seeded_prs/` – PRs with known bugs, used to check the reviewer (to do)
- `results/` – results and links to every run, PR and review (to do)

The hidden acceptance tests for the issues are kept outside the repo while the runs happen, so the
agents can't see them. I'll add them under `experiment/hidden_tests/` at the end.

## AI use

I used Claude Code to help with setting up the fork, checking the ADRs for consistency, and writing
parts of the docs and code. I went through everything it produced. The design decisions and the
reasoning in the ADRs are my own.
