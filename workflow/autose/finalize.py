"""After each review round: record how many review rounds are used and tell the issue what
happened. No model. This is the only place that writes review_rounds_used (ADR-004).

    python -m autose.finalize --issue 3 --round 1 \
        --results '{"plan":"success",...}' --verdict APPROVE --routing none --last

--round is the overall review round for this issue (1 or 2), counted across runs.
"""
import argparse
import json
import os
import sys

from . import github

STAGE_OF_JOB = {"plan": "Stage 1-2 (planner)", "build": "Stage 3-4 (builder)",
                "release": "Stage 5 (release)", "ci": "Stage 5 (CI)", "review": "Stage 6 (review)"}


def outcome(results: dict, verdict: str, routing: str, is_last: bool) -> tuple[str, bool]:
    """Return (sentence for the issue, whether a review round was completed)."""
    for job, result in results.items():
        if result in ("failure", "cancelled"):
            return f"Stopped at {STAGE_OF_JOB.get(job, job)}: the check didn't pass. See the run's artifacts.", False
    if results.get("review") != "success":
        return "Nothing to review this time.", False
    if verdict == "APPROVE":
        return "The reviewer approved. The PR is ready for a person to review and merge.", True
    if is_last:
        return ("The reviewer still asks for changes and both review rounds are used. "
                "Over to a person now."), True
    return f"The reviewer asked for changes; sending it back to the {routing} step.", True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--results", default="{}")
    parser.add_argument("--verdict", default="")
    parser.add_argument("--routing", default="")
    parser.add_argument("--last", action="store_true")
    args = parser.parse_args()

    results = {k: v for k, v in json.loads(args.results).items() if v}
    sentence, reviewed = outcome(results, args.verdict, args.routing, args.last)
    run_url = (f"{os.environ.get('GITHUB_SERVER_URL')}/{github.repo()}/actions/runs/"
               f"{os.environ.get('GITHUB_RUN_ID')}")
    used = args.round if reviewed else args.round - 1
    github.update_state(args.issue, review_rounds_used=used, last_stage=f"finalize-r{args.round}",
                        last_run=run_url, note=f"round {args.round}: {sentence}")
    github.gh("issue", "comment", str(args.issue), "--repo", github.repo(),
              "--body", f"AutoSE round {args.round}: {sentence} ([run]({run_url}))")
    print(sentence)
    return 0


if __name__ == "__main__":
    sys.exit(main())
