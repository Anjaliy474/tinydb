"""Agent 3, the independent Reviewer: Stage 6 (ADR-008).

Runs in its own job with a read-only checkout of the PR head. It gets the issue and the diff,
nothing from the other agents. It posts a COMMENT review (the bot can't approve its own PR, and
approval belongs to a person anyway).

    python -m autose.review --issue 3 --pr 7 --round 1
"""
import argparse
import json
import os
import subprocess
import sys

from . import config as cfg
from . import gates, github
from .budget import Budget, BudgetExceeded
from .llm import AgentError, make_agent
from .tools import Workspace, reviewer_tools

MAX_DIFF = 40_000


def render(review: dict, round_no: int, model: str) -> tuple[str, str]:
    """Return (review.md, the text posted on the PR)."""
    verdict = review["verdict"]
    head = ("**Reviewer verdict: APPROVE**" if verdict == "APPROVE" else
            f"**Reviewer verdict: REQUEST_CHANGES** (goes back to {review['routing_target']})")
    parts = [head, "", review.get("summary", ""), ""]
    for dim in gates.DIMENSIONS:
        item = review.get(dim) or {}
        mark = "ok" if item.get("ok") else "problem"
        parts.append(f"- {dim.replace('_', ' ')} ({mark}): {item.get('finding', '')}")
    defects = review.get("defects") or []
    if defects:
        parts += ["", "Defects:"]
        parts += [f"- `{d['file']}:{d['line']}` {'(blocking) ' if d['blocking'] else ''}"
                  f"{d['description']}" for d in defects]
    parts += ["", f"Tests run: `{review.get('tests_command', '')}` -> exit {review.get('tests_exit_code')}",
              "", f"_Review round {round_no}, model {model}. A person decides whether to merge._"]
    comment = "\n".join(parts)
    md = "\n".join(["---", "stage: 6", f"round: {round_no}", f"verdict: {verdict}",
                    f"routing_target: {review['routing_target']}", f"reviewer_model: {model}",
                    "---", "# Review", "", comment, "", "```json",
                    json.dumps(review, indent=2), "```", ""])
    return md, comment


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--round", type=int, default=1)
    args = parser.parse_args()

    conf = cfg.load()
    out = cfg.artifacts_dir()
    base = subprocess.run(["git", "merge-base", f"origin/{conf['base_branch']}", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    ws = Workspace(conf, base, out)
    budget = Budget(conf["budget"]["review_usd_per_round"], conf["budget"]["review_tokens_per_round"],
                    f"review-r{args.round}")
    model = conf.model("reviewer")
    issue = github.fetch_issue(args.issue)
    diff = ws.git_diff()
    if len(diff) > MAX_DIFF:
        diff = diff[:MAX_DIFF] + "\n[... diff cut, use git_diff or read_file for the rest ...]"
    # AUTOSE_REVIEWER_PROMPT picks the prompt variant for the experiments (intake checks it).
    prompt_name = os.environ.get("AUTOSE_REVIEWER_PROMPT") or "reviewer"
    if prompt_name not in ("reviewer", "reviewer_plain"):
        prompt_name = "reviewer"
    agent = make_agent(model=model, system=cfg.prompt(prompt_name), tools=reviewer_tools(ws),
                  budget=budget, max_turns=conf.limit("reviewer_turns"), effort="high")
    try:
        agent.send(github.issue_prompt(issue, conf.limit("issue_max_chars")) +
                   f"\n\nPull request #{args.pr} diff:\n\n```diff\n{diff}\n```\n\nReview it.")
        review = ws.submitted["review"]
        ran_tests = any(e.get("tool") == "run_tests" and not e.get("error") for e in agent.log)
        result = gates.gate_review(review, args.round, ran_tests)
        md, comment = render(review, args.round, f"{model}, {prompt_name} prompt")
        (out / "review.md").write_text(md, encoding="utf-8")
        if not result.passed:
            gates.add_diagnostics(out / "review.md", result)
            print("Stage 6 check failed: " + "; ".join(result.reasons))
            return 1
        github.gh("pr", "review", str(args.pr), "--repo", github.repo(), "--comment",
                  "--body-file", "-", input_text=comment)
        github.set_output(verdict=review["verdict"], routing=review["routing_target"])
        print(comment)
        return 0
    except (AgentError, BudgetExceeded, KeyError) as exc:
        (out / "review.md").write_text("---\nstage: 6\nstatus: failed\n---\n# Review failed\n",
                                       encoding="utf-8")
        gates.add_diagnostics(out / "review.md", gates.GateResult(False, [f"reviewer stopped: {exc}"]))
        print(f"Stage 6 failed: {exc}")
        return 1
    finally:
        budget.save(out)


if __name__ == "__main__":
    sys.exit(main())
