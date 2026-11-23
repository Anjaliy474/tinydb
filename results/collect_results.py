"""Collect every AutoSE run from GitHub into results/results.csv and results/runs.md.

Reads only real data: the Actions API (jobs and their results) and each run's artifacts
(run_state.json for tokens and cost, review.md for the verdict). Hidden-test results are added
from hidden_results.json, which I fill in by running the hidden tests on each PR branch.

    python collect_results.py   (from Assignment_3, with gh logged in)
"""
import csv
import json
import pathlib
import re
import subprocess
import tempfile

GH = r"C:\Program Files\GitHub CLI\gh.exe"
REPO = "Anjaliy474/tinydb"
HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE  # this copy lives in results/; the working copy ran from the folder above the repo
SEEDS = {"24": "S1", "25": "S2", "26": "S3", "27": "S4", "29": "S5"}
STAGES = ["planner", "builder (round 1)", "release (round 1)", "CI (round 1)",
          "independent review (round 1)", "review-only"]


def gh_json(*args):
    out = subprocess.run([GH, *args], capture_output=True, text=True, encoding="utf-8")
    return json.loads(out.stdout or "null")


def artifacts(run_id: int) -> dict:
    """Download a run's artifacts and pull out tokens, cost, verdict, model and prompt."""
    info = {"tokens": 0, "usd": 0.0, "verdict": "", "routing": "", "reviewer_model": "",
            "prompt": "", "probes": "", "test_runs": "", "blocking": "", "review_turns": ""}
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([GH, "run", "download", str(run_id), "--repo", REPO, "-D", tmp],
                       capture_output=True)
        seen = set()
        for state in pathlib.Path(tmp).rglob("run_state.json"):
            for stage in json.loads(state.read_text(encoding="utf-8")).get("stages", []):
                key = (stage["stage"], stage["tokens"], stage["usd"])
                if key not in seen:  # artifacts of later jobs repeat earlier stages
                    seen.add(key)
                    info["tokens"] += stage["tokens"]
                    info["usd"] += stage["usd"]
        for review in pathlib.Path(tmp).rglob("review.md"):
            text = review.read_text(encoding="utf-8")
            m = re.search(r"^verdict: (\w+)", text, re.M)
            if m:
                info["verdict"] = m.group(1)
            m = re.search(r"^reviewer_model: ([^,\n]+)(?:, (\w+) prompt)?", text, re.M)
            if m:
                info["reviewer_model"], info["prompt"] = m.group(1).strip(), (m.group(2) or "")
            m = re.search(r"^routing_target: (\w+)", text, re.M)
            if m:
                info["routing"] = m.group(1)
            m = re.search(r"```json\n(.*?)\n```", text, re.S)
            if m:
                try:
                    data = json.loads(m.group(1))
                    info["blocking"] = sum(1 for d in data.get("defects", [])
                                           if isinstance(d, dict) and d.get("blocking"))
                except json.JSONDecodeError:
                    pass
        for log in pathlib.Path(tmp).rglob("review-r*_agent_log.json"):
            agents = json.loads(log.read_text(encoding="utf-8"))
            calls = [e for a in agents for e in a.get("log", []) if e.get("tool")]
            info["probes"] = sum(1 for e in calls if e["tool"] == "run_python")
            info["test_runs"] = sum(1 for e in calls if e["tool"] == "run_tests")
            info["review_turns"] = sum(a.get("turns", 0) for a in agents)
    info["usd"] = round(info["usd"], 4)
    return info


def main():
    hidden = json.loads((HERE / "hidden_results.json").read_text()) if (HERE / "hidden_results.json").exists() else {}
    runs = gh_json("run", "list", "--repo", REPO, "--workflow", "AutoSE", "--limit", "200",
                   "--json", "databaseId,displayTitle,event,conclusion,createdAt,url")
    rows = []
    for run in sorted(runs, key=lambda r: r["createdAt"]):
        jobs = gh_json("run", "view", str(run["databaseId"]), "--repo", REPO, "--json", "jobs")["jobs"]
        if all(j["conclusion"] == "skipped" for j in jobs if j["name"] != "intake"):
            continue  # intake said no (wrong comment etc.)
        result = {s: "" for s in STAGES}
        for job in jobs:
            for s in STAGES:
                if job["name"].endswith(s):
                    result[s] = job["conclusion"]
        info = artifacts(run["databaseId"])
        mode = "review-only" if result["review-only"] not in ("", "skipped") else "full"
        key = str(run["databaseId"])
        names = gh_json("api", f"repos/{REPO}/actions/runs/{key}/artifacts", "--jq",
                        "[.artifacts[].name]") or []
        pr = next((n.removeprefix("review-pr-") for n in names if n.startswith("review-pr-")), "")
        rows.append({
            "run_id": run["databaseId"], "date": run["createdAt"][:16].replace("T", " "),
            "title": run["displayTitle"], "pr_reviewed": pr, "seed": SEEDS.get(pr, ""),
            "mode": mode, "conclusion": run["conclusion"],
            **{f"stage_{s.split(' ')[0].lower()}": result[s] for s in STAGES if s != "review-only"},
            "review_only": result["review-only"], "verdict": info["verdict"],
            "routing": info["routing"], "blocking_defects": info["blocking"],
            "probes": info["probes"], "test_runs": info["test_runs"],
            "review_turns": info["review_turns"],
            "reviewer_model": info["reviewer_model"], "prompt": info["prompt"],
            "tokens": info["tokens"], "usd": info["usd"],
            "hidden_tests": hidden.get(key, ""), "url": run["url"],
        })
        print(f"{key} {mode} {run['conclusion']} {info['verdict']} {info['tokens']}")
    OUT.mkdir(exist_ok=True)
    with open(OUT / "results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# Runs", "", "Every AutoSE run, in order. Generated by `collect_results.py` from the "
             "GitHub Actions API and the runs' artifacts.", "",
             "| Run | Date (UTC) | Issue / PR | Mode | Result | Verdict | Reviewer | Tokens | Est. cost | Hidden tests |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        reviewer = f"{r['reviewer_model']} ({r['prompt']})" if r["reviewer_model"] else ""
        lines.append(f"| [{r['run_id']}]({r['url']}) | {r['date']} | {r['title']} | {r['mode']} | "
                     f"{r['conclusion']} | {r['verdict']} | {reviewer} | {r['tokens']} | "
                     f"${r['usd']} | {r['hidden_tests']} |")
    total_t = sum(r["tokens"] for r in rows)
    total_usd = round(sum(r["usd"] for r in rows), 4)
    lines += ["", f"Total: {total_t} tokens, about ${total_usd} (Gemini free-tier runs count as $0)."]
    (OUT / "runs.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"total tokens {total_t}, usd {total_usd}")


if __name__ == "__main__":
    main()
