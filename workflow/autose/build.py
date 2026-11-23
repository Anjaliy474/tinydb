"""Agent 2, the Builder: Stage 3 (diff.patch) and Stage 4 (test_report.md), with the bounded
retry loop from ADR-002.

One cycle = up to `attempts_per_cycle` attempts in one conversation, so the builder keeps its
context while fixing failures. If a cycle runs out (or the same failure repeats), the Planner
revises the design once, and the builder gets one more cycle from a clean tree.

    python -m autose.build --round 1
    python -m autose.build --round 2 --review review.md --route implementation
"""
import argparse
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from . import config as cfg
from . import gates
from .budget import Budget, BudgetExceeded
from .llm import Agent, AgentError, ModelUnavailable, make_agent, save_agent_logs
from .plan import run_design
from .tools import Workspace, builder_tools, tail


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True).stdout.strip()


def reset_tree(repo: Path, base: str) -> None:
    git(repo, "reset", "-q")
    git(repo, "checkout", "-q", base, "--", ".")
    git(repo, "clean", "-fdq")


def first_message(spec: str, design: str, review: str) -> str:
    msg = f"spec.md:\n\n{spec}\n\ndesign.md:\n\n{design}\n"
    if review:
        msg += ("\nAn independent reviewer asked for changes to the current code. Fix what it "
                f"found:\n\n{review}\n")
    return msg + "\nImplement the change and its tests, then call submit_work."


def run(conf: cfg.Config, out: Path, round_no: int, review: str = "", route: str = "",
        budget: Optional[Budget] = None, client=None,
        make_builder: Optional[Callable[[Workspace], Agent]] = None) -> int:
    repo = conf.repo_root
    base = git(repo, "rev-parse", "HEAD")
    from .github import set_output
    set_output(base_sha=base)
    budget = budget or Budget(conf["budget"]["build_usd_per_round"], conf["budget"]["build_tokens_per_round"],
                              f"build-r{round_no}")
    spec = (out / "spec.md").read_text(encoding="utf-8")
    design_path = out / "design.md"
    criteria = gates.acceptance_criteria(spec)
    history: list[str] = []

    models = conf.models("builder")
    current = {"index": 0}

    def builder(ws: Workspace) -> Agent:
        if make_builder:
            return make_builder(ws)
        return make_agent(model=models[current["index"]],
                     system=cfg.prompt("builder", allowed_paths=", ".join(conf.allowed_paths)),
                     tools=builder_tools(ws), budget=budget,
                     max_turns=conf.limit("builder_turns"), client=client)

    def revise_design(reason: str) -> bool:
        plan_ws = Workspace(conf, base, out)
        result = run_design(conf, plan_ws, budget, spec, reason, client=client)
        history.append(f"design revised: {'passed' if result.passed else 'FAILED'}")
        if not result.passed:
            gates.add_diagnostics(design_path, result)
        return result.passed

    try:
        if route == "design" and not revise_design(review):
            return finish(out, round_no, criteria, None, history, "design revision failed")

        code, _, junit = gates.run_junit(conf)
        baseline_skipped = junit["skipped"]
        history.append(f"baseline: exit {code}, {len(junit['cases'])} tests, {baseline_skipped} skipped")

        cycles = 1 + conf.limit("design_escalations")
        for cycle in range(1, cycles + 1):
            if cycle > 1:
                reset_tree(repo, base)
            ws = Workspace(conf, base, out)
            agent = builder(ws)
            opening = first_message(spec, design_path.read_text(encoding="utf-8"),
                                    review if route == "implementation" else "")
            message = opening
            last_signature, failure = None, ""
            for attempt in range(1, conf.limit("attempts_per_cycle") + 1):
                label = f"cycle {cycle} attempt {attempt}"
                try:
                    while True:
                        try:
                            agent.send(message)
                            break
                        except ModelUnavailable as exc:
                            # Out of quota or overloaded: start this attempt again on the next
                            # model in the list, from a clean tree (ADR-011).
                            if current["index"] + 1 >= len(models):
                                raise
                            history.append(f"{label}: {models[current['index']]} unavailable "
                                           f"({exc}); switching to {models[current['index'] + 1]}")
                            current["index"] += 1
                            reset_tree(repo, base)
                            ws = Workspace(conf, base, out)
                            agent = builder(ws)
                            message = opening
                except ModelUnavailable as exc:
                    # Every builder model is out: a design revision wouldn't help, stop now.
                    history.append(f"{label}: no builder model available: {exc}")
                    return finish(out, round_no, criteria, None, history,
                                  f"no builder model available ({exc})")
                except AgentError as exc:
                    failure = f"builder stopped: {exc}"
                    history.append(f"{label}: {failure}")
                    break
                g3 = gates.gate_implementation(conf, base)
                if not g3.passed:
                    failure = "Stage 3 check failed:\n- " + "\n- ".join(g3.reasons)
                    signature = "g3:" + "|".join(g3.reasons)
                else:
                    (out / "diff.patch").write_text(g3.data["patch"], encoding="utf-8")
                    mapping = ws.submitted.get("work", {}).get("ac_mapping", [])
                    g4 = gates.gate_tests(conf, criteria, mapping, g3.data["files"], baseline_skipped)
                    if g4.passed:
                        history.append(f"{label}: passed")
                        return finish(out, round_no, criteria, (mapping, g4), history, "",
                                      ws.submitted.get("work", {}).get("summary", ""))
                    failure = ("Stage 4 check failed:\n- " + "\n- ".join(g4.reasons) +
                               "\n\nTest output (end):\n" + tail(g4.data["output"], 6000))
                    signature = g4.data["signature"] or "|".join(g4.reasons)
                history.append(f"{label}: {failure.splitlines()[0]}")
                if signature == last_signature:
                    history.append(f"{label}: same failure twice in a row, ending this cycle")
                    break
                last_signature = signature
                message = failure + "\n\nFix this and call submit_work again."
            if cycle < cycles:
                reason = ("The builder could not make the tests pass with this design. "
                          f"Last failure:\n\n{tail(failure, 4000)}")
                if not revise_design(reason):
                    return finish(out, round_no, criteria, None, history, "design revision failed")
        return finish(out, round_no, criteria, None, history, failure or "no passing attempt")
    except (BudgetExceeded, AgentError) as exc:  # e.g. the design revision hit an API error
        history.append(str(exc))
        return finish(out, round_no, criteria, None, history, str(exc))
    finally:
        budget.save(out)
        save_agent_logs(out, f"build-r{round_no}")
        # The reviewer job uses this to stay off the builder's model (ADR-008, ADR-011).
        set_output(builder_model=models[current["index"]])


def finish(out: Path, round_no: int, criteria: dict, passed, history: list[str], error: str,
           summary: str = "") -> int:
    ok = passed is not None
    lines = ["---", "stage: 4", f"round: {round_no}", f"status: {'ok' if ok else 'failed'}",
             f"gate_passed: {str(ok).lower()}", "---", "# Test report", ""]
    if ok:
        mapping, g4 = passed
        tests = {m["ac"]: m["test"] for m in mapping}
        lines += ["| Criterion | Test | Result |", "|---|---|---|"]
        lines += [f"| {ac} | `{tests.get(ac, '-')}` | passed |" for ac in criteria]
        last = [l for l in g4.data["output"].splitlines() if l.strip()][-1:]  # noqa: E741
        lines += ["", f"Full suite: {last[0] if last else 'passed'}", "", f"Summary: {summary}"]
    else:
        lines += [f"The builder could not finish: {error}", ""]
    lines += ["", "## Attempts", ""] + [f"- {h}" for h in history]
    (out / "test_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--review", help="review.md from the previous round")
    parser.add_argument("--route", choices=["implementation", "design"], default=None)
    args = parser.parse_args()
    review = Path(args.review).read_text(encoding="utf-8") if args.review else ""
    return run(cfg.load(), cfg.artifacts_dir(), args.round, review, args.route or "")


if __name__ == "__main__":
    sys.exit(main())
