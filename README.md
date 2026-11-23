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

All agents run on DeepSeek's API. Every role uses `deepseek-flash` (DeepSeek V4.1 Flash-1017).
Release and CI are plain scripts with no model.

This is the third model setup. I started with Claude (ADR-006), had no paid access, moved to
Gemini's free tier (ADR-011), and moved again to DeepSeek when four of five free-tier runs failed
on rate limits and quotas (ADR-013). The code still supports all three: the model names in
`.autose.yml` decide which one is used.

## Running it

On any issue in this repo, a maintainer either adds the label `autose` or writes a comment starting
with `/autose`. Labels and comments from other people are ignored. If two runs start for the same
issue, the second one waits for the first. `/autose reset` starts the review-round count again.

`/autose review` on any open PR that says which issue it fixes (`Fixes #N`) runs only the
independent reviewer. For experiments it takes `model=<name>` and `prompt=plain`.

To set it up in your own fork you need to:

1. Turn on Issues in the repo settings.
2. In Settings → Actions → General, allow GitHub Actions to create pull requests.
3. Add `DEEPSEEK_API_KEY` as a repository secret (or `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` with
   matching model names in `.autose.yml`).
4. Top up only a small balance with the provider before the first run.

## Results

All five test issues went through the whole workflow and got a PR that the reviewer approved and
that passes my hidden acceptance tests:

| Issue | PR | Hidden tests |
| :--- | :--- | :--- |
| #2 remove() with duplicate ids | [#19](https://github.com/Anjaliy474/tinydb/pull/19) | 3/3 |
| #3 fragment() on two fields | [#16](https://github.com/Anjaliy474/tinydb/pull/16) | 3/3 |
| #4 rename operation | [#23](https://github.com/Anjaliy474/tinydb/pull/23) | 3/3 |
| #5 search limit | [#20](https://github.com/Anjaliy474/tinydb/pull/20) | 4/4 |
| #6 dates (the vague one) | [#28](https://github.com/Anjaliy474/tinydb/pull/28) | 3/3 |

On five seeded PRs (four with a planted bug, one clean), the reviewer caught all four bugs and
approved the clean one, with each of the three reviewer setups I tried
([experiment/variants.md](experiment/variants.md)). Every run, with its link, tokens and cost, is
in [results/runs.md](results/runs.md). All runs together used about 5.9 million tokens, roughly
$0.85 on DeepSeek; the Gemini runs were free.

None of these PRs are merged. That's left to a person, on purpose.

## What's in this repo

- `architecture/decisions/` – the ADRs, one per design decision; superseded ones are kept
- `architecture/views/` – component view, stage map, and the sequence view of a real run
- `.github/workflows/` – the workflows GitHub runs; `workflow/github/` is a copy of them
- `workflow/` – agent code, prompts and the harness tests
- `experiment/issues/` – the five issues I opened to test the workflow
- `experiment/hidden_tests/` – the hidden acceptance tests (added after all runs were done)
- `experiment/seeded_prs/` – the seeded PR diffs and which bug each one has
- `experiment/variants.md` – the two reviewer experiments and what they showed
- `results/` – `results.csv`, `runs.md` and the script that builds them from GitHub
- `report/` – the report (`report.pdf`), the demo video (`demo.mp4`) and its script

## AI use

I used Claude Code to help with setting up the fork, checking the ADRs for consistency, and writing
parts of the docs and code. I went through everything it produced. The design decisions and the
reasoning in the ADRs are my own.
