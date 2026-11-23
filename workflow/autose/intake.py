"""Job 0: decide whether this event should start a run (ADR-010, ADR-004). No model is used.

Reads the event payload GitHub gives us, never interpolates issue text into a shell.
Outputs: proceed, issue, rounds_left, reason.
"""
import json
import os
import re
import sys

from . import config as cfg
from . import github

MAINTAINERS = {"OWNER", "MEMBER", "COLLABORATOR"}


def decide(event_name: str, event: dict, conf: dict, lookup_pr_branch=None, comments=None) -> dict:
    def stop(reason):
        return {"proceed": "false", "issue": "", "rounds_left": "0", "first_round": "0",
                "reason": reason}

    sender = (event.get("sender") or {}).get("login", "")
    if sender.endswith("[bot]"):
        return stop("event sent by a bot")
    issue = event.get("issue") or {}
    if issue.get("state") != "open":
        return stop("issue or PR is not open")

    reset = False
    if event_name == "issues":
        if event.get("action") != "labeled" or (event.get("label") or {}).get("name") != conf["trigger_label"]:
            return stop("not the trigger label")
        # Only users with triage access or more can add labels, so this is already a maintainer.
    elif event_name == "issue_comment":
        comment = event.get("comment") or {}
        body = (comment.get("body") or "").strip()
        if not body.startswith(conf["trigger_command"]):
            return stop("comment is not a trigger command")
        if comment.get("author_association") not in MAINTAINERS:
            return stop("comment author is not a maintainer")
        reset = body.split()[1:2] == ["reset"]
    else:
        return stop(f"unsupported event {event_name}")

    number = issue["number"]
    if "pull_request" in issue:
        # A command on the PR: map it back to its issue through the branch name.
        branch = lookup_pr_branch(number) if lookup_pr_branch else ""
        match = re.fullmatch(r"autose/issue-(\d+)", branch or "")
        if not match:
            return stop("PR was not opened by AutoSE")
        number = int(match.group(1))

    state, _ = github.read_state(comments(number) if comments else [])
    used = 0 if reset or not state else int(state.get("review_rounds_used", 0))
    rounds_left = conf["limits"]["review_rounds"] - used
    if rounds_left <= 0:
        return stop("both review rounds are used up; a person needs to take over "
                    f"(or comment `{conf['trigger_command']} reset`)")
    return {"proceed": "true", "issue": str(number), "rounds_left": str(rounds_left),
            "first_round": str(used + 1), "reason": "ok" + (" (reset)" if reset else "")}


def main() -> int:
    conf = cfg.load().raw
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        event = json.load(f)
    result = decide(
        os.environ["GITHUB_EVENT_NAME"], event, conf,
        lookup_pr_branch=lambda n: github.gh_json(
            "pr", "view", str(n), "--repo", github.repo(), "--json", "headRefName")["headRefName"],
        comments=github.issue_comments,
    )
    print(f"intake: {result}")
    github.set_output(**result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
