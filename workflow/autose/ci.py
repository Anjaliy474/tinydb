"""Stage 5 check: run CI at the PR head and post an `autose/ci` commit status. No model.

    python -m autose.ci --pr 7 --sha <head sha> --round 1
"""
import argparse
import json
import os
import sys

from . import config as cfg
from . import gates, github
from .tools import run_command, tail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--round", type=int, default=1)
    args = parser.parse_args()

    conf = cfg.load()
    out = cfg.artifacts_dir()
    lines = ["---", "stage: 5", f"round: {args.round}", "---", "# CI on the PR head", "",
             f"Commit `{args.sha}`", ""]
    passed = True
    for cmd in conf["ci_cmds"]:
        code, output = run_command(cmd, conf.repo_root, 600)
        passed = passed and code == 0
        lines += [f"## `{cmd}` (exit {code})", "", "```", tail(output, 3000), "```", ""]

    pr = github.gh_json("pr", "view", str(args.pr), "--repo", github.repo(),
                        "--json", "number,url,state,baseRefName,headRefName")
    pr["repo"] = github.repo()
    result = gates.gate_release(pr, conf, ci_passed=passed)
    lines.insert(3, f"status: {'ok' if result.passed else 'failed'}")
    (out / "ci.md").write_text("\n".join(lines), encoding="utf-8")

    run_url = (f"{os.environ.get('GITHUB_SERVER_URL')}/{github.repo()}/actions/runs/"
               f"{os.environ.get('GITHUB_RUN_ID')}")
    status = {"state": "success" if passed else "failure", "context": "autose/ci",
              "description": "tests and type check" + ("" if passed else " failed"),
              "target_url": run_url}
    github.gh("api", "-X", "POST", f"repos/{github.repo()}/statuses/{args.sha}",
              "--input", "-", input_text=json.dumps(status))

    if not result.passed:
        gates.add_diagnostics(out / "ci.md", result)
        print("Stage 5 check failed: " + "; ".join(result.reasons))
        return 1
    print("Stage 5 check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
