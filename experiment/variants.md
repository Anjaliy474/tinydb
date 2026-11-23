# Decision experiments

Two ADRs tested on the same five seeded PRs (`seeded_prs/`). Four of them have a bug I planted on
purpose and one is a correct fix; all five pass TinyDB's own test suite, so a reviewer can't find
the bugs just by running the tests. The answer key is in `seeded_prs/labels.md`; it was kept
outside the repo until every review had finished, because the reviewer can read the repository.

Every review was started with a `/autose review` comment on the PR, so each one ran in its own
read-only job with no artifacts from other stages (ADR-008). Run links are in
`results/runs.md`; the numbers below come from `results/results.csv`.

## The variants

| Variant | What changes | How it was started |
| :--- | :--- | :--- |
| Baseline | `deepseek-flash` with the default skeptical prompt (`workflow/prompts/reviewer.md`) | `/autose review` |
| A: stronger reviewer model (tests ADR-008 / ADR-013) | Same prompt, `deepseek-v4-pro` instead of `deepseek-flash` | `/autose review model=deepseek-v4-pro` |
| B: plain prompt (tests ADR-008's anti-sycophancy prompt) | Same model, `reviewer_plain.md`: no "assume it's wrong", no request for edge-case probes | `/autose review prompt=plain` |

Everything else is the same in all three: tools, turn limit (25), the Stage 6 gate (verdict
format, all four audit dimensions, tests must have been run, blocking defects need file and line).

## Results

Expected verdicts: S1-S4 request changes, S5 approve. S1's planted problem is in the approach
(fragment queries made uncacheable), so the expected routing for S1 is `design`; S2-S4 are code
bugs (`implementation`).

| Seed | Planted | Baseline (Flash, skeptical) | A (Pro, skeptical) | B (Flash, plain) |
| :--- | :--- | :--- | :--- | :--- |
| S1 | fragment queries uncacheable; equality bug stays | changes, implementation | changes, **design** | changes, implementation |
| S2 | dedup in remove() only | changes | changes | changes (after a format repair) |
| S3 | limit applied before caching | changes | changes | changes |
| S4 | rename crashes on docs without the old field | changes | changes | changes |
| S5 | none | approve | approve | approve |
| **Caught / false alarms** | | **4/4, 0** | **4/4, 0** | **4/4, 0** |
| Routing right on S1 | | no | yes | no |
| Probes run (S1-S5) | | 2, 2, 3, 2, 7 | 4, 2, 2, 4, 3 | 3, 2, 2, 2, 3 |
| Turns (S1-S5) | | 7, 7, 6, 7, 19 | 11, 7, 6, 14, 14 | 11, 7, 6, 6, 12 |
| Tokens, all 5 | | 713K | 635K | 339K (valid reviews; the crashed run used 39K more) |
| Est. cost, all 5 | | $0.059 | $0.196 | $0.038 |

The first plain-prompt review of S2 crashed: the model sent one finding as `true` instead of an
object, which the review code didn't handle. After adding the one format-repair pass that ADR-007
allows, the rerun produced a valid review. The crashed run is kept in `results/runs.md`.

## What I take from it

- **Detection didn't depend on either decision here.** All three variants caught all four planted
  bugs and approved the clean PR. On these seeds the separate job, the evidence-gated rubric and
  the four-dimension checklist seem to do most of the work; the skeptical wording and the bigger
  model added no catches. That is a negative result for both ADRs as they are stated.
- **The skeptical prompt made the reviewer more careful before approving.** On the clean S5 it ran
  7 probes and used 19 turns before approving, against 3 probes / 12 turns with the plain prompt.
  It didn't change the verdicts, but it is the behaviour ADR-008 wanted: approval is earned.
- **The bigger model routed the design problem correctly.** Only Pro sent S1 back to the design
  stage; both Flash variants called it an implementation problem. With routing, that decides
  whether round 2 re-plans or just patches, so it matters more than the verdict alone suggests.
  It cost about 3.3 times as much as the Flash baseline.
- **What I changed:** nothing in the default setup yet. The evidence supports keeping the cheap
  Flash reviewer with the skeptical prompt, and it suggests Pro is worth it only where routing
  matters. A design change I'd make next is to use Pro only for REQUEST_CHANGES verdicts, to
  confirm the routing.

## Limits of this experiment

- Five seeds, one review per variant per seed. A 4/4 vs 4/4 tie says little about the cases where
  the variants would differ; harder or subtler seeds would be needed to separate them.
- I wrote the seeds and the reviewer prompts, so the seeds may suit what the prompts ask for.
- The seeded tests' names contain the word "seeded" (one review noticed it), which could hint
  that the PR is a test.
- Model output varies from run to run; with one run per cell, a single different verdict would
  change the picture.
