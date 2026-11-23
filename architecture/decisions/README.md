# Architecture Decision Records — AutoSE Agentic SDLC Workflow

- **Scope:** Repository-agnostic GitHub Actions agentic SDLC workflow (configured per repository via `.autose.yml`)
- **Format:** [Michael Nygard ADR format](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions) (`Title`, `Status`, `Context`, `Decision`, `Consequences`)
- **Date:** 2026-11-23

## Decision Summary Table

| ADR | Decision | Option Chosen | Main Option Rejected | Main Reason | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| [ADR-001](ADR-001.md) | **D1: Splitting the Work** | 3 specialized LLM agents (Planner: 1–2, Builder: 3–4, Independent Reviewer: 6) + deterministic Stage 5 Release script | 1 monolithic agent or 6 one-per-stage agents | Minimizes token overhead and cold starts while preserving read-only planning, deterministic release, and strict reviewer isolation | Accepted |
| [ADR-002](ADR-002.md) | **D2: Control Flow** | Finite deterministic FSM inside an unrolled multi-job Actions DAG (max 3 test retries per cycle, 1 design escalation per round, max 2 review rounds; CI run in-workflow) | Open-ended LLM planner / dynamic router | Structurally guarantees finite termination, zero orchestration tokens, and single-run traceability | Accepted |
| [ADR-003](ADR-003.md) | **D3: Hand-offs** | Minimal schema-validated Markdown + YAML artifacts with strict omissions (Stage 6 sees only issue + diff + repo) | Forwarding full agent transcripts across stages | Cuts input tokens, contains prompt injection, and prevents reviewer anchor bias | Accepted |
| [ADR-004](ADR-004.md) | **D4: State** | Dual-layer: Actions workflow artifacts (intra-run) + `autose/issue-<N>` branch & hidden bot-comment JSON checkpoint (inter-run) | Committing `.autose/` artifacts onto the feature branch | Keeps target-repo PR diffs clean, hides Stage 1–5 files from Stage 6, and makes restarts idempotent | Accepted |
| [ADR-005](ADR-005.md) | **D5: Tools** | Minimal role-scoped Python tool wrappers + deterministic `gh` CLI + workflow `permissions: {}` with per-job `GITHUB_TOKEN` grants | GitHub MCP Server Docker container in every job | Lower latency and smaller tool schemas (fewer tokens) with platform-enforced least privilege | Accepted |
| [ADR-006](ADR-006.md) | **D6: Models** | Role-tiered env-configured routing (Sonnet 5.5 Planner/Builder, Haiku 5.5 Stage 1 judge, no LLM for Stage 5, GPT-5 Reviewer) | Same model across all 6 stages | Controls cost while giving Stage 6 cross-family model diversity to reduce correlated blind spots | Accepted |
| [ADR-007](ADR-007.md) | **D7: Checks** | Deterministic-first gate runner (`workflow/gates.py`) for Stages 1–6 + Haiku 5.5 testability rubric for Stage 1 only | Agent self-certification or LLM judge for every stage | Objective build/test/symbol/CI oracles prevent hallucinated passes and save tokens | Accepted |
| [ADR-008](ADR-008.md) | **D8: Reviewer Independence** | 4-pillar isolation: separate job (`contents: read`, `COMMENT`-only review), no upstream artifacts, cross-family model, execution-backed adversarial rubric | Same-job review prompt or static diff-only review | Stops sycophantic approvals via mandatory test execution, 4-dimension audit, and `seeded_prs/` calibration | Accepted |
| [ADR-009](ADR-009.md) | **D9: Safety & Failures** | Tight job/subprocess timeouts, $2.50 & 200K token/turn/retry caps, `env:`-safe issue fetch, path allowlist, stripped test-env secrets | Default 6-hour timeouts and prompt-only safety | Deterministically prevents runaway costs, Actions script injection, and secret exfiltration | Accepted |
| [ADR-010](ADR-010.md) | **D10: Triggers** | Maintainer-gated `issues.labeled` (`autose`) + `issue_comment.created` (`/autose`) with per-issue `concurrency:` queuing | Auto-trigger on `issues.opened` or repo-wide global lock | Protects API budget on public forks, prevents branch races, and allows parallel runs across issues | Accepted |
