"""Thin wrappers around the gh CLI, plus the status comment that holds run state (ADR-004)."""
import json
import os
import re
import subprocess
from typing import Optional

BOT = "github-actions[bot]"
MARKER = re.compile(r"<!-- autose-state: (\{.*?\}) -->")


def gh(*args: str, input_text: Optional[str] = None) -> str:
    out = subprocess.run(["gh", *args], capture_output=True, text=True, input=input_text,
                         encoding="utf-8", check=True)
    return out.stdout


def gh_json(*args: str):
    return json.loads(gh(*args) or "null")


def repo() -> str:
    return os.environ["GITHUB_REPOSITORY"]


def fetch_issue(number: int) -> dict:
    return gh_json("issue", "view", str(number), "--repo", repo(), "--json", "number,title,body,state")


def clean_untrusted(text: str, limit: int) -> str:
    """Issue text is attacker-controlled: drop control characters and cut it to size."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text or "")
    text = text.replace("</untrusted_issue_data>", "")
    return text[:limit]


def issue_prompt(issue: dict, limit: int) -> str:
    title = clean_untrusted(issue.get("title", ""), 300)
    body = clean_untrusted(issue.get("body", ""), limit)
    return (f"<untrusted_issue_data>\nIssue #{issue['number']}: {title}\n\n{body}\n"
            f"</untrusted_issue_data>")


# --- run state in the bot's status comment -------------------------------------------------

def read_state(comments: list[dict]) -> tuple[Optional[dict], Optional[int]]:
    """Return (state, comment id) from the newest status comment written by the bot.

    Markers in comments by anyone else are ignored, so nobody can fake the state.
    """
    for comment in reversed(comments):
        login = (comment.get("user") or {}).get("login")
        if login != BOT:
            continue
        match = MARKER.search(comment.get("body") or "")
        if match:
            try:
                return json.loads(match.group(1)), comment.get("id")
            except json.JSONDecodeError:
                continue
    return None, None


def render_state(state: dict) -> str:
    rows = "\n".join(f"| {k} | {v} |" for k, v in state.items() if k != "history")
    history = "\n".join(f"- {h}" for h in state.get("history", []))
    return (f"**AutoSE status**\n\n| | |\n|---|---|\n{rows}\n\n{history}\n\n"
            f"<!-- autose-state: {json.dumps(state, separators=(',', ':'))} -->")


def issue_comments(number: int) -> list[dict]:
    return gh_json("api", f"repos/{repo()}/issues/{number}/comments?per_page=100")


def update_state(number: int, **changes) -> dict:
    state, comment_id = read_state(issue_comments(number))
    state = state or {"issue": number, "review_rounds_used": 0, "history": []}
    note = changes.pop("note", None)
    state.update(changes)
    if note:
        state.setdefault("history", []).append(note)
    body = json.dumps({"body": render_state(state)})
    if comment_id:
        gh("api", "-X", "PATCH", f"repos/{repo()}/issues/comments/{comment_id}", "--input", "-",
           input_text=body)
    else:
        gh("api", "-X", "POST", f"repos/{repo()}/issues/{number}/comments", "--input", "-",
           input_text=body)
    return state


def set_output(**values) -> None:
    """Write step outputs for GitHub Actions (or print them when run locally)."""
    path = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{k}={v}" for k, v in values.items()]
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))
