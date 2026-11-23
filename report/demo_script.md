# Demo video script (about 4:30, limit 5:00)

Plain spoken English, first person. Scenes 6-9 are the one complete run the assignment asks for:
issue #2, run 45186252584, PR #19, from the issue page to the posted review.

| # | On screen | Voice-over |
|---|---|---|
| 1 | Title, repo link | Hi. This is my Assignment 3 for AutoSE. The task was to build a GitHub Actions workflow where agents take a GitHub issue and turn it into a tested and reviewed pull request. A maintainer only adds a label or a comment. A person still decides whether to merge. I did this on a fork of TinyDB, pinned to commit edff96a. |
| 2 | Stage table: the six stages, artifact and check | The assignment fixes six stages. Requirements writes spec.md. Design writes design.md. Implementation changes the code. Testing runs the old and new tests. Release opens the pull request and runs CI. Review is done by a separate agent. Each stage saves a file, and the next stage starts only if a check passes. |
| 3 | Component diagram | I used three agents. The Planner does requirements and design. The Builder does implementation and testing. The Reviewer does the review. Release and CI are plain scripts with no model. The pass or fail decision is made by normal code in gates.py, not by the agent. This is a fixed pipeline, so every run ends in a known number of steps. |
| 4 | How work is passed + reviewer independence | The agents pass only small files to each other, not their conversations. The Reviewer runs in its own job. It sees only the issue, the diff and the code. It never sees the spec or the Builder's notes, and it cannot push or merge. It has to run the tests, and every problem it reports needs a file and a line. |
| 5 | Permissions, triggers, safety | Each job gets only the GitHub permissions it needs. Only the release job can push. Only a maintainer can start a run, and two runs on the same issue wait for each other. Issue text is treated as untrusted. It never goes into a shell command, and secrets are removed before any test runs. Every stage has limits on turns, tokens, cost and time. |
| 6 | Issue #2 page | Now one complete run. Issue 2 is a bug: remove crashes when the same id is passed twice. I start the workflow by commenting slash autose. |
| 7 | Actions run page + job times + artifacts | The whole run took about six minutes. The Planner's first spec failed the check, so it got one chance to fix it, and then it passed with six testable criteria. The design named the exact functions to change. The Builder fixed update and remove, added six tests, and all 239 tests passed. All the files from each stage are saved with the run. |
| 8 | PR #19 + CI | The release job opened pull request 19 and ran CI on it. The description shows each acceptance criterion and the test that checks it. |
| 9 | Review comment on PR #19 | This is the review. The Reviewer read the code, ran the tests and tried some edge cases itself, and then approved. The pull request is now waiting for me to decide. |
| 10 | Results table + pass-rate chart | I opened five issues: two bugs, two features and one vague one. For each, I wrote hidden tests that the agents never saw. All five got a pull request that passed review and passed all sixteen hidden tests. In total I made fourteen full runs. They used about 5.9 million tokens and cost about 85 cents. |
| 11 | Seeded PR #27 review + experiment table | To check the Reviewer, I made five pull requests myself. Four had a bug I planted, and one was correct. The Reviewer caught all four bugs and approved the correct one. I also tested two decisions: a stronger model for the Reviewer, and a plain prompt instead of a strict one. The verdicts did not change. The strict prompt made it check more carefully, and only the stronger model saw that one bug was a design problem. |
| 12 | Model timeline + ADR list | I wrote thirteen ADRs. Three decisions changed after real runs. I planned to use Claude but had no paid access. I moved to the Gemini free tier, but it kept running out of quota, so I moved to DeepSeek. I kept the old ADRs and marked them superseded. If I started again, I would check model access first. |
| 13 | Limitations + repo layout | There are limits. The sample is small, I wrote the tests myself, and round two of the review never happened, because every pull request was approved the first time. Everything is in the repository: the report, the ADRs, the workflow code, the experiments and all the run links. Thank you. |

## Links used
- Repo: https://github.com/Anjaliy474/tinydb
- Issue #2: https://github.com/Anjaliy474/tinydb/issues/2
- Run: https://github.com/Anjaliy474/tinydb/actions/runs/45186252584
- PR #19: https://github.com/Anjaliy474/tinydb/pull/19
- Seeded PR #27: https://github.com/Anjaliy474/tinydb/pull/27
