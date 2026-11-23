"""Job 0: decide whether this event should start a run (ADR-010, ADR-004). No model is used.

Reads the event payload GitHub gives us, never interpolates issue text into a shell.

Two modes:
- full:   the `autose` label on an issue, or `/autose` on an issue or on an AutoSE PR.
- review: `/autose review` on any open PR runs only the independent reviewer on it. Used for the
          seeded PRs and the reviewer experiments. Options: `model=<gemini model>` and
          `prompt=default|plain`.

Outputs: proceed, mode, issue, pr, rounds_left, first_round, review_model, review_prompt, reason.
"""
import json
import os
import re
import sys

from . import config as cfg
from . import github

MAINTAINERS = {"OWNER", "MEMBER", "COLLABORATOR"}
MODEL_NAME = re.compile(r"(gemini|claude)-[a-z0-9.-]+")
PROMPTS = {"default": "reviewer", "plain": "reviewer_plain"}


def parse_review_options(words: list[str]) -> dict | str:
    """Return the options, or an error message. Only known, safe values get through."""
    options = {"review_model": "", "review_prompt": "reviewer"}
    for word in words:
        key, _, value = word.partition("=")
        if key == "model" and MODEL_NAME.fullmatch(value):
            options["review_model"] = value
        elif key == "prompt" and value in PROMPTS:
            options["review_prompt"] = PROMPTS[value]
        else:
            return f"unknown review option {word[:40]!r}"
    return options


def decide(event_name: str, event: dict, conf: dict, lookup_pr=None, comments=None) -> dict:
    def stop(reason):
        return {"proceed": "false", "mode": "", "issue": "", "pr": "", "rounds_left": "0",
                "first_round": "0", "review_model": "", "review_prompt": "", "reason": reason}

    sender = (event.get("sender") or {}).get("login", "")
    if sender.endswith("[bot]"):
        return stop("event sent by a bot")
    issue = event.get("issue") or {}
    if issue.get("state") != "open":
        return stop("issue or PR is not open")

    words: list[str] = []
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
        words = body.splitlines()[0].split()[1:]
    else:
        return stop(f"unsupported event {event_name}")

    number = issue["number"]
    is_pr = "pull_request" in issue

    if words[:1] == ["review"]:
        if not is_pr:
            return stop("`review` only works on a pull request")
        options = parse_review_options(words[1:])
        if isinstance(options, str):
            return stop(options)
        pr = lookup_pr(number) if lookup_pr else {}
        linked = re.search(r"(?:fixes|closes|resolves)\s+#(\d+)", pr.get("body") or "", re.I)
        branch = re.fullmatch(r"autose/issue-(\d+)", pr.get("headRefName") or "")
        target = linked or branch
        if not target:
            return stop("can't tell which issue this PR is for (add 'Fixes #N' to its description)")
        return {"proceed": "true", "mode": "review", "issue": target.group(1), "pr": str(number),
                "rounds_left": "1", "first_round": "1", **options, "reason": "review only"}

    reset = words[:1] == ["reset"]
    if words and not reset:
        return stop(f"unknown command {words[0][:40]!r}")
    if is_pr:
        # A command on an AutoSE PR: map it back to its issue through the branch name.
        branch = (lookup_pr(number) if lookup_pr else {}).get("headRefName", "")
        match = re.fullmatch(r"autose/issue-(\d+)", branch or "")
        if not match:
            return stop("PR was not opened by AutoSE (use `/autose review` to only review it)")
        number = int(match.group(1))

    state, _ = github.read_state(comments(number) if comments else [])
    used = 0 if reset or not state else int(state.get("review_rounds_used", 0))
    rounds_left = conf["limits"]["review_rounds"] - used
    if rounds_left <= 0:
        return stop("both review rounds are used up; a person needs to take over "
                    f"(or comment `{conf['trigger_command']} reset`)")
    return {"proceed": "true", "mode": "full", "issue": str(number), "pr": "",
            "rounds_left": str(rounds_left), "first_round": str(used + 1),
            "review_model": "", "review_prompt": "reviewer",
            "reason": "ok" + (" (reset)" if reset else "")}


def main() -> int:
    conf = cfg.load().raw
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        event = json.load(f)
    result = decide(
        os.environ["GITHUB_EVENT_NAME"], event, conf,
        lookup_pr=lambda n: github.gh_json(
            "pr", "view", str(n), "--repo", github.repo(), "--json", "headRefName,body"),
        comments=github.issue_comments,
    )
    print(f"intake: {result}")
    github.set_output(**result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
