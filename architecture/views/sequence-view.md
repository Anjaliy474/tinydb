# Sequence View: one real run, issue #2 to its review

This is [run 45186252584](https://github.com/Anjaliy474/tinydb/actions/runs/45186252584) on
[issue #2](https://github.com/Anjaliy474/tinydb/issues/2) ("remove() crashes if the same id is
passed twice"), started by a `/autose` comment. It produced
[PR #19](https://github.com/Anjaliy474/tinydb/pull/19), which passes all three hidden tests, and an
APPROVE review. Times are UTC on 23 Nov 2026; tokens and tool calls come from the run's artifacts
(`run_state.json` and the `*_agent_log.json` files).

At the time of this run the planner and builder used `deepseek-flash` and the reviewer used
`deepseek-v4-pro` (ADR-013). Later runs use `deepseek-flash` for every role.

```mermaid
sequenceDiagram
    autonumber
    actor M as Maintainer
    participant GH as GitHub (issue, PR, status comment)
    participant IN as intake job
    participant PL as plan job: Planner (Flash)
    participant G as gates.py
    participant BU as build job: Builder (Flash)
    participant RE as release job (no model)
    participant CI as ci job (no model)
    participant RV as review job: Reviewer (Pro)
    participant FI as finalize job (no model)

    M->>GH: comment "/autose" on issue #2 (13:40:30)
    GH->>IN: issue_comment event
    IN->>IN: maintainer? command? rounds left? (bot-written state only)
    IN-->>GH: proceed, issue=2, rounds_left=2

    Note over PL: 13:40:49 to 13:42:05
    PL->>GH: status comment "run started: planning"
    PL->>PL: Stage 1: read issue (untrusted), file list, ARCHITECTURE.md, code
    PL->>G: spec.md
    G-->>PL: rejected, reasons sent back
    PL->>G: revised spec.md (one revision, ADR-012)
    G->>G: plain checks + testability judge (Flash)
    G-->>PL: Stage 1 passed, 6 acceptance criteria
    PL->>G: Stage 2: design.md
    G-->>PL: files and symbols exist, Stage 2 passed
    PL-->>GH: artifact r1-plan (spec.md, design.md)

    Note over BU: 13:42:08 to 13:43:16, contents: read, no token in .git
    BU->>BU: baseline: 228 tests pass
    BU->>BU: 20 turns: read 8, search 3, edit 13, build 2, tests 2
    BU->>G: submit_work (AC-1..6 mapped to tests)
    G->>G: Stage 3: diff allowed paths, git apply, build
    G->>G: Stage 4: full suite 239 passed, every AC mapped to a passing new test
    G-->>BU: passed on attempt 1
    BU-->>GH: artifact r1-build (diff.patch, test_report.md)

    Note over RE: 13:43:19 to 13:43:42, the only job allowed to push
    RE->>GH: push autose/issue-2, open PR #19 ("Fixes #2")
    RE->>G: Stage 5: PR open, right base and branch, in the fork
    RE->>GH: status comment: PR link

    Note over CI: 13:43:45 to 13:44:11
    CI->>CI: pytest + mypy at the PR head
    CI->>GH: commit status autose/ci = success

    Note over RV: 13:44:14 to 13:46:24, sees only issue + diff + code
    RV->>RV: 11 turns: diff, read 7, search 2, run_tests 1, probes 3
    RV->>G: submit_review
    G->>G: Stage 6: 4 dimensions, tests were run, verdict format
    RV->>GH: COMMENT review "Reviewer verdict: APPROVE"

    FI->>GH: review_rounds_used=1, comment on issue #2 (13:46:43)
    GH-->>M: PR #19 waits for a person to merge
```

## Per stage

| Stage | Job | Wall time | Model calls | Tokens | Est. cost |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1-2 Requirements, design | plan | 1 min 16 s | 15 | 170,336 | $0.022 |
| 3-4 Implementation, testing | build-r1 | 1 min 8 s | 20 | 295,821 | $0.014 |
| 5 Release | release-r1 | 23 s | 0 | 0 | $0 |
| 5 Check: CI | ci-r1 | 26 s | 0 | 0 | $0 |
| 6 Independent review | review-r1 | 2 min 10 s | 11 | 165,688 | $0.053 |
| Whole run | | **6 min 13 s** | 46 | 631,845 | **$0.089** |

Things this run shows about the design:

- The planner's first spec failed a gate and was fixed in the same conversation, without a person
  (ADR-012).
- The builder never saw the issue text, only `spec.md` and `design.md` (ADR-003).
- Only the release job had write access, and it ran no model (ADR-001, ADR-005).
- CI ran inside the workflow, because pushes made with the workflow's token don't start other
  workflows (ADR-002).
- The reviewer ran on a different model, never downloaded the planner's or builder's artifacts,
  and approved only after running the tests and three probes of its own (ADR-008).
- Nothing was merged. The run ends with a PR and a review for a person to judge.
