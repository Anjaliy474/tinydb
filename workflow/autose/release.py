"""Stage 5, Release. A plain script, no model (ADR-001).

Applies diff.patch on the autose/issue-N branch, pushes it, and opens or updates the PR.
CI runs in the next job, because pushes made with GITHUB_TOKEN don't trigger other workflows.

    python -m autose.release --issue 3 --round 1
"""
import argparse
import os
import re
import subprocess
import sys

from . import config as cfg
from . import gates, github


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def pr_body(issue: dict, report: str, round_no: int) -> str:
    table = "\n".join(l for l in report.splitlines() if l.startswith("|"))  # noqa: E741
    summary = next((l[len("Summary: "):] for l in report.splitlines()  # noqa: E741
                    if l.startswith("Summary: ")), "")
    run_url = (f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
               f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}")
    return (f"Fixes #{issue['number']}\n\n{summary}\n\n{table}\n\n"
            f"Opened by the AutoSE workflow ([run]({run_url}), review round {round_no}). "
            "The spec, design and test report are attached to the run as artifacts. "
            "A separate reviewer agent will comment on this PR. The bot never merges, "
            "so please review before merging.\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--round", type=int, default=1)
    args = parser.parse_args()

    conf = cfg.load()
    out = cfg.artifacts_dir()
    if github.repo() != conf["fork_repo"]:
        print(f"refusing to release: running in {github.repo()}, not {conf['fork_repo']}")
        return 1
    branch = f"autose/issue-{args.issue}"
    if branch == conf["base_branch"] or not re.fullmatch(r"autose/issue-\d+", branch):
        print("refusing to push to this branch")
        return 1

    issue = github.fetch_issue(args.issue)
    report = (out / "test_report.md").read_text(encoding="utf-8")

    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    if args.round == 1:
        git("checkout", "-B", branch)
    git("apply", "--index", str(out / "diff.patch"))
    title = github.clean_untrusted(issue["title"], 120)
    message = (f"{title} (#{args.issue})" if args.round == 1
               else f"Address review comments (#{args.issue})")
    git("commit", "-q", "-m", message)
    if args.round == 1:
        git("push", "--force", "origin", f"HEAD:refs/heads/{branch}")
    else:
        git("push", "origin", f"HEAD:refs/heads/{branch}")
    head_sha = git("rev-parse", "HEAD")

    body = pr_body(issue, report, args.round)
    existing = github.gh_json("pr", "list", "--repo", github.repo(), "--head", branch,
                              "--state", "open", "--json", "number")
    if existing:
        number = existing[0]["number"]
        github.gh("pr", "edit", str(number), "--repo", github.repo(), "--body", body)
    else:
        url = github.gh("pr", "create", "--repo", github.repo(), "--base", conf["base_branch"],
                        "--head", branch, "--title", title, "--body", body).strip()
        number = int(url.rstrip("/").split("/")[-1])
    pr = github.gh_json("pr", "view", str(number), "--repo", github.repo(),
                        "--json", "number,url,state,baseRefName,headRefName")
    pr["repo"] = github.repo()

    result = gates.gate_release(pr, conf, ci_passed=None)
    lines = ["---", "stage: 5", f"round: {args.round}",
             f"status: {'ok' if result.passed else 'failed'}", f"pr: {pr['url']}",
             f"head_sha: {head_sha}", "---", f"# Pull request\n\n{pr['url']}\n", body]
    (out / "pr.md").write_text("\n".join(lines), encoding="utf-8")
    if not result.passed:
        gates.add_diagnostics(out / "pr.md", result)
        print("Stage 5 failed: " + "; ".join(result.reasons))
        return 1
    github.update_state(args.issue, pr=number, last_stage=f"release-r{args.round}",
                        note=f"round {args.round}: PR {pr['url']} updated at {head_sha[:7]}")
    github.set_output(pr_number=number, pr_url=pr["url"], head_sha=head_sha)
    print(f"Stage 5: {pr['url']} at {head_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
