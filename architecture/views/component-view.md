# Component View — AutoSE Issue-to-PR Workflow

This view shows every component, the tools each one may use, the GitHub token permissions of the
Actions job it runs in, and how components call each other. It reflects ADR-001 (split), ADR-002
(control flow), ADR-005 (tools) and ADR-008 (reviewer independence).

```mermaid
flowchart LR
    subgraph GH["GitHub (fork: Anjaliy474/tinydb)"]
        ISSUE["Issue + label 'autose'<br/>or comment '/autose'"]
        PR["Pull request<br/>branch autose/issue-N"]
        STATUS["Status comment<br/>hidden autose-state JSON"]
        ART[("Actions workflow artifacts<br/>spec.md, design.md, diff.patch,<br/>test_report.md, pr.md, review.md,<br/>run_state.json")]
    end

    subgraph WF[".github/workflows/autose.yml (one run)"]
        INTAKE["intake job<br/>trigger filter, maintainer check,<br/>restart checkpoint<br/><i>no LLM</i>"]

        subgraph PLAN["plan job · contents:read, issues:write"]
            A1["Agent 1: Planner<br/>Stage 1 Requirements, Stage 2 Design<br/>model: Sonnet 5.5"]
            J1["Testability judge<br/>Haiku 5.5"]
            T1["tools: read_file, list_files,<br/>search_code, write_artifact"]
        end

        subgraph BUILD["build-r1 / rework-r2 job · contents:read"]
            ORCH["orchestrator.py<br/>bounded FSM: 3 attempts per cycle,<br/>1 design escalation"]
            A2["Agent 2: Builder<br/>Stage 3 Implement, Stage 4 Test<br/>model: Sonnet 5.5"]
            A1b["Agent 1 (fresh context)<br/>Stage 2 only, on escalation"]
            T2["tools: read_file, edit_file (allowlist),<br/>run_build, run_tests, git_diff,<br/>write_artifact"]
        end

        subgraph REL["release-r1 / release-r2 job · contents:write, pull-requests:write, issues:write"]
            S5["Release script, Stage 5<br/><i>no LLM</i><br/>git push, gh pr create/edit, render pr.md"]
        end

        subgraph CI["ci-r1 / ci-r2 job · contents:read, statuses:write"]
            S5C["In-run CI, Stage 5 check<br/><i>no LLM</i><br/>ci_cmds at PR head, post autose/ci status"]
        end

        subgraph REV["review-r1 / review-r2 job · contents:read, pull-requests:write"]
            A3["Agent 3: Independent Reviewer<br/>Stage 6<br/>model: GPT-5 (fallback Opus 5.5)"]
            T3["tools: read_file, search_code,<br/>git_diff, run_tests, write_artifact;<br/>gh pr review --comment"]
        end

        GATES["gates.py<br/>deterministic pass/fail for every stage"]
        BUDGET["budget.py<br/>token/cost/turn caps"]
    end

    HUMAN(["Maintainer<br/>merges or closes"])

    ISSUE -->|issues.labeled / issue_comment.created| INTAKE
    INTAKE -->|issue number via env| PLAN
    A1 --- T1
    A1 --> J1
    PLAN -->|spec.md, design.md| BUILD
    ORCH --> A2
    ORCH -->|tests keep failing| A1b
    A2 --- T2
    BUILD -->|diff.patch, test_report.md| REL
    S5 --> PR
    REL --> CI
    S5C -->|commit status| PR
    CI --> REV
    PR -->|issue, diff, repo at PR head ONLY| A3
    A3 --- T3
    A3 -->|COMMENT review + verdict| PR
    REV -->|REQUEST_CHANGES: code issue| BUILD
    REV -->|REQUEST_CHANGES: approach issue| A1b
    GATES -.checks.-> PLAN & BUILD & REL & CI & REV
    BUDGET -.caps.-> PLAN & BUILD & REV
    PLAN & BUILD & REL & CI & REV -.upload.-> ART
    INTAKE & REL -.update.-> STATUS
    REV -->|approve, or 2 rounds used| HUMAN
```

## What each component can and cannot do

| Component | Job permissions | Can | Cannot |
| :--- | :--- | :--- | :--- |
| Intake | `issues: read` | Read the trigger event, check the actor's repo permission, read the status comment | Call any model |
| Agent 1: Planner | `contents: read`, `issues: write` | Read the repo, write `spec.md` / `design.md`, update the status comment | Edit code, run shell commands, push |
| Agent 2: Builder | `contents: read` | Edit files inside `allowed_edit_paths`, run build and tests locally | Push, call `gh` write commands, edit `.github/` or `workflow/` |
| Release script | `contents: write`, `pull-requests: write`, `issues: write` | Push `autose/issue-N`, open or update the PR | Merge, push to `master`, run a model |
| In-run CI | `contents: read`, `statuses: write` | Run `ci_cmds`, post the `autose/ci` status | Change code, PRs or issues |
| Agent 3: Reviewer | `contents: read`, `pull-requests: write` | Read the issue, diff and repo at PR head, run tests, post a `COMMENT` review | Push, approve, merge, read Stage 1–5 artifacts |

## Information Barriers

- The Reviewer job never runs `actions/download-artifact`, so it cannot see `spec.md`, `design.md`,
  `test_report.md`, `pr.md` or any agent transcript (ADR-003, ADR-008).
- Untrusted issue text reaches only Agent 1 (Stage 1) and Agent 3, both read-only. The Builder
  works from `spec.md` and `design.md`, which have passed their gates (ADR-003, ADR-009).
- `gates.py`, not the agents, decides pass or fail and which stage runs next (ADR-007).
