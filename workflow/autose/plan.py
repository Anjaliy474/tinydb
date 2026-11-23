"""Agent 1, the Planner: Stage 1 (spec.md) and Stage 2 (design.md). Read-only tools.

    python -m autose.plan --issue 3                     # Stages 1 and 2
    python -m autose.plan --design-only --reason r.md   # revise design.md (escalation / review)
"""
import argparse
import sys
from pathlib import Path

from . import config as cfg
from . import gates, github
from .budget import Budget, BudgetExceeded
from .llm import Agent, AgentError, ask_json
from .tools import Workspace, planner_tools


def run_spec(conf, ws, budget, issue: dict, client=None) -> gates.GateResult:
    agent = Agent(model=conf.model("planner"), system=cfg.prompt("planner_spec"),
                  tools=planner_tools(ws, "spec.md"), budget=budget,
                  max_turns=conf.limit("planner_turns"), client=client)
    agent.send(github.issue_prompt(issue, conf.limit("issue_max_chars")) +
               "\n\nWrite spec.md for this issue.")
    spec = ws.submitted.get("spec.md", "")

    def judge(criteria):
        listing = "\n".join(f"{k}: {v}" for k, v in criteria.items())
        return ask_json(model=conf.model("judge"), system=cfg.prompt("judge"),
                        user=f"Repository: TinyDB (Python).\n\nCriteria:\n{listing}",
                        schema=gates.JUDGE_SCHEMA, budget=budget, client=client)

    return gates.gate_spec(spec, judge)


def run_design(conf, ws, budget, spec: str, reason: str = "", client=None) -> gates.GateResult:
    allowed = ", ".join(conf.allowed_paths)
    agent = Agent(model=conf.model("planner"),
                  system=cfg.prompt("planner_design", allowed_paths=allowed),
                  tools=planner_tools(ws, "design.md"), budget=budget,
                  max_turns=conf.limit("planner_turns"), client=client)
    architecture = (conf.repo_root / conf["architecture_doc"]).read_text(encoding="utf-8")
    message = f"spec.md:\n\n{spec}\n\nARCHITECTURE.md:\n\n{architecture}\n"
    if reason:
        message += f"\nRevise the design. Reason:\n\n{reason}\n"
    agent.send(message + "\nWrite design.md.")
    return gates.gate_design(ws.submitted.get("design.md", ""), conf)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", type=int)
    parser.add_argument("--design-only", action="store_true")
    parser.add_argument("--reason", help="file with the reason for a design revision")
    args = parser.parse_args()

    conf = cfg.load()
    out = cfg.artifacts_dir()
    ws = Workspace(conf, "HEAD", out)
    budget = Budget(conf["budget"]["plan_usd"], conf["budget"]["run_tokens"], "plan")
    try:
        if not args.design_only:
            github.update_state(args.issue, last_stage="plan", note="run started: planning")
            issue = github.fetch_issue(args.issue)
            result = run_spec(conf, ws, budget, issue)
            if not result.passed:
                return fail(out / "spec.md", result, "Stage 1")
            print("Stage 1 passed")
        spec = (out / "spec.md").read_text(encoding="utf-8")
        reason = Path(args.reason).read_text(encoding="utf-8") if args.reason else ""
        result = run_design(conf, ws, budget, spec, reason)
        if not result.passed:
            return fail(out / "design.md", result, "Stage 2")
        print("Stage 2 passed")
        return 0
    except (AgentError, BudgetExceeded) as exc:
        name = "design.md" if args.design_only or (out / "spec.md").exists() else "spec.md"
        return fail(out / name, gates.GateResult(False, [str(exc)]), "Planner")
    finally:
        budget.save(out)


def fail(path: Path, result: gates.GateResult, stage: str) -> int:
    if not path.exists():
        path.write_text(f"---\nstatus: failed\n---\n# {stage} failed\n", encoding="utf-8")
    gates.add_diagnostics(path, result)
    print(f"{stage} failed: " + "; ".join(result.reasons))
    return 1


if __name__ == "__main__":
    sys.exit(main())
