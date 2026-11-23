# Stage Map — Agent, Artifact and Check per Stage

| # | Stage | Agent / component | Actions job | Artifact | Check before moving on (enforced by `gates.py`) | On failure |
| :- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Requirements | Agent 1: Planner (A1 spec skill) + testability judge (model) | `plan` | `spec.md` | Valid frontmatter; ≥ 2 `AC-i` criteria with precondition and expected outcome; no vague words; judge marks every `AC-i` testable | One revision with the reasons (ADR-012), then explain in `spec.md` and halt |
| 2 | Design | Agent 1: Planner (uses `ARCHITECTURE.md`) | `plan` | `design.md` | Every named file exists (or is tagged `[NEW]`); every named function/class exists; all paths inside `allowed_edit_paths` | One revision with the reasons (ADR-012), then explain in `design.md` and halt |
| 3 | Implementation | Agent 2: Builder | `build-r1` / `rework-r2` | `diff.patch` | Non-empty diff; paths inside allowlist; `git apply --check`; `build_cmd` exits 0 | Retry within the cycle (max 3 attempts) |
| 4 | Testing | Agent 2: Builder | `build-r1` / `rework-r2` | `test_report.md` | `test_cmd` exits 0 (old + new tests); every `AC-i` maps to a passing test; no new skips | Back to Stage 3; after a used-up cycle, one escalation to Stage 2; then halt |
| 5 | Release | Release script (no LLM) + in-run CI | `release-r1` → `ci-r1` (and `-r2`) | `pr.md` + PR link | PR is `OPEN` in the fork; `ci-r1` passed and `autose/ci` status is `success` | Explain in `pr.md`, halt run |
| 6 | Review | Agent 3: Independent Reviewer | `review-r1` / `review-r2` | `review.md` | Valid verdict JSON; all 4 audit dimensions covered; test-run evidence recorded; defects cite file and line; round ≤ 2 | `REQUEST_CHANGES` goes to Stage 3 (code) or Stage 2 (approach), once; after round 2, a person decides |

Bounds per run: at most 2 review rounds; per round, at most 2 Builder cycles of 3 attempts and 1
design escalation; plus the token, cost and time caps in ADR-009. The workflow never merges.
