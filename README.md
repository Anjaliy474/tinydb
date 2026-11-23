# AutoSE Assignment 3: Agentic SDLC Workflow (Issue In, Pull Request Out)

Roll no: 2025204015

This fork adds a GitHub Actions workflow in which agents turn a labelled issue into a tested,
independently reviewed pull request. A person always makes the final merge decision.

- **Fork:** https://github.com/Anjaliy474/tinydb
- **Upstream:** https://github.com/msiemens/tinydb
- **Pinned commit:** `edff96aeb2616402e9489d46e90a592c05565621` (tag `autose-base`), the same commit used in A2
- **Original TinyDB README:** [`README.rst`](README.rst)

## Status

Design phase. This commit contains only the architecture (ADRs and views). The design was
committed before any agent code was written, as the assignment requires.

## Models (ADR-006)

| Role | Model |
| :--- | :--- |
| Agent 1: Planner (Stages 1–2) | Claude Sonnet 5.5 (`claude-sonnet-5-5`) |
| Agent 2: Builder (Stages 3–4) | Claude Sonnet 5.5 (`claude-sonnet-5-5`) |
| Stage 1 testability judge | Claude Haiku 5.5 (`claude-haiku-5-5`) |
| Stage 5 Release and CI | No model (deterministic script) |
| Agent 3: Independent Reviewer (Stage 6) | OpenAI GPT-5; falls back to Claude Opus 5.5 (`claude-opus-5-5`) if no OpenAI key is set |

## How to trigger the workflow (ADR-010)

A maintainer (write, maintain or admin access) does one of the following on an issue:

1. Adds the label `autose`, or
2. Posts a comment starting with `/autose`.

Comments and labels from anyone else are ignored. Runs on the same issue are queued, never run in parallel.

## Repository layout

| Path | Contents |
| :--- | :--- |
| `architecture/decisions/` | ADR-001 … ADR-010 (Nygard format), plus a summary table in `README.md` |
| `architecture/views/` | Component view, stage map (the sequence view is added after the first real run) |
| `workflow/` | Copy of `.github/workflows/` and all agent code and prompts *(to come)* |
| `experiment/` | Issues, seeded PRs, experiment variants *(to come; hidden tests are kept outside the repo)* |
| `results/` | `results.csv`, `runs.md` *(to come)* |

## AI use

I used Claude Code (Claude Opus 5.5) to help set up the fork, fix consistency issues in the ADRs,
and draft the architecture views. I reviewed all generated content. The ADRs and the design
reasoning are my own.
