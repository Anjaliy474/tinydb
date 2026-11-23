"""Agent 1, the Planner: Stage 1 (spec.md) and Stage 2 (design.md). Read-only tools.

    python -m autose.plan --issue 3                     # Stages 1 and 2
    python -m autose.plan --design-only --reason r.md   # revise design.md (escalation / review)
"""
import argparse
import subprocess
import sys
from pathlib import Path

from . import config as cfg
from . import gates, github
from .budget import Budget, BudgetExceeded
from .llm import (AgentError, ModelUnavailable, ask_json_any as ask_json, make_agent,
                  run_with_fallback, save_agent_logs)
from .tools import Workspace, planner_tools


def repo_context(conf, with_architecture: bool = True) -> str:
    """The file list (and ARCHITECTURE.md) up front, so the planner doesn't spend a model call
    on every directory listing. On the free tier each call can mean a wait (ADR-011)."""
    files = [f for f in ws_files(conf) if f.startswith(tuple(conf.allowed_paths))]
    text = "Files in the repository you may plan changes to:\n" + "\n".join(files)
    if with_architecture:
        doc = (conf.repo_root / conf["architecture_doc"]).read_text(encoding="utf-8")
        text += f"\n\nARCHITECTURE.md:\n\n{doc}"
    return text


def ws_files(conf) -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=conf.repo_root, capture_output=True, text=True)
    return [line for line in out.stdout.splitlines() if line]


def run_spec(conf, ws, budget, issue: dict, client=None) -> gates.GateResult:
    return run_with_fallback(conf.models("planner"),
                             lambda m: _run_spec(conf, ws, budget, issue, client, m), "planner")


def _run_spec(conf, ws, budget, issue: dict, client, model: str) -> gates.GateResult:
    agent = make_agent(model=model, system=cfg.prompt("planner_spec"),
                  tools=planner_tools(ws, "spec.md"), budget=budget,
                  max_turns=conf.limit("planner_turns"), client=client)
    agent.send(github.issue_prompt(issue, conf.limit("issue_max_chars")) + "\n\n" +
               repo_context(conf) +
               "\n\nRead only the source files you need, then write spec.md for this issue.")

    def judge(criteria):
        listing = "\n".join(f"{k}: {v}" for k, v in criteria.items())

        def ask(judge_model):
            return ask_json(model=judge_model, system=cfg.prompt("judge"),
                            user=f"Repository: TinyDB (Python).\n\nCriteria:\n{listing}",
                            schema=gates.JUDGE_SCHEMA, budget=budget, client=client)
        try:
            return run_with_fallback(conf.models("judge"), ask, "judge")
        except ModelUnavailable as exc:  # a judge problem must not switch the planner's model
            raise AgentError(f"testability check unavailable: {exc}") from exc

    return check_with_revision(conf, agent, ws, "spec.md",
                               lambda text: gates.gate_spec(text, judge))


def run_design(conf, ws, budget, spec: str, reason: str = "", client=None) -> gates.GateResult:
    return run_with_fallback(conf.models("planner"),
                             lambda m: _run_design(conf, ws, budget, spec, reason, client, m),
                             "planner")


def _run_design(conf, ws, budget, spec: str, reason: str, client, model: str) -> gates.GateResult:
    allowed = ", ".join(conf.allowed_paths)
    agent = make_agent(model=model,
                  system=cfg.prompt("planner_design", allowed_paths=allowed),
                  tools=planner_tools(ws, "design.md"), budget=budget,
                  max_turns=conf.limit("planner_turns"), client=client)
    message = f"spec.md:\n\n{spec}\n\n{repo_context(conf)}\n"
    if reason:
        message += f"\nRevise the design. Reason:\n\n{reason}\n"
    agent.send(message + "\nRead the files you plan to change, then write design.md.")
    return check_with_revision(conf, agent, ws, "design.md",
                               lambda text: gates.gate_design(text, conf))


def check_with_revision(conf, agent, ws, name: str, gate) -> gates.GateResult:
    """Run the stage's gate. If it fails, show the planner the checker's reasons and let it
    rewrite the artifact, at most `plan_revisions` times (one by default). The gate still makes
    the final decision. Added after the second run on #3, where one vague criterion stopped the
    whole run (see the note in ADR-007)."""
    result = gate(ws.submitted.get(name, ""))
    for attempt in range(conf.limit("plan_revisions")):
        if result.passed or gates.front_matter(ws.submitted.get(name, "")).get("status") == "blocked":
            break
        print(f"{name} check failed, asking the planner to revise it: " + "; ".join(result.reasons))
        agent.max_turns += 4  # room for the revision on top of the normal turn limit
        reasons = "\n".join(f"- {r}" for r in result.reasons)
        agent.send(f"The checker rejected {name}:\n{reasons}\n\n"
                   f"Fix exactly these problems, keep everything else, and call write_artifact "
                   f"again with the whole corrected {name}.")
        result = gate(ws.submitted.get(name, ""))
        result.data["revisions"] = attempt + 1
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", type=int)
    parser.add_argument("--design-only", action="store_true")
    parser.add_argument("--reason", help="file with the reason for a design revision")
    args = parser.parse_args()

    conf = cfg.load()
    out = cfg.artifacts_dir()
    ws = Workspace(conf, "HEAD", out)
    budget = Budget(conf["budget"]["plan_usd"], conf["budget"]["plan_tokens"], "plan")
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
        save_agent_logs(out, "plan")


def fail(path: Path, result: gates.GateResult, stage: str) -> int:
    if not path.exists():
        path.write_text(f"---\nstatus: failed\n---\n# {stage} failed\n", encoding="utf-8")
    gates.add_diagnostics(path, result)
    print(f"{stage} failed: " + "; ".join(result.reasons))
    return 1


if __name__ == "__main__":
    sys.exit(main())
