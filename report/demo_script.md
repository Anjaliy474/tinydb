# Demo video script (about 5 minutes)

Record the screen with your voice. Use a run you start live, or replay a finished one (issue #2,
run 45186252584, took about 6 minutes, so a live run fits if you talk over the waiting).

**0:00 - 0:30 The idea.** Open the repo README. "A maintainer labels an issue, agents turn it into a
tested, reviewed PR, and a person decides whether to merge. Most of the work is in the design, so
I'll show a run and then why it's built this way."

**0:30 - 1:00 The issue.** Open an issue (for a live run, a new small one, or #2). Point at how short
and informal it is. Add the `autose` label (or comment `/autose`).

**1:00 - 2:00 The run.** Open the Actions tab. Show the job graph: intake, planner, builder, release,
CI, review, finalize. Click the planner job and show the live log lines (`[deepseek] ... turn 3`,
"Stage 1 passed"). Say: each stage is its own job with only the permissions it needs; only the
release job can push.

**2:00 - 2:45 The artifacts.** On the run page, open the artifacts: `spec.md` (Given/When/Then
criteria), `design.md` (files and functions), `test_report.md` (each criterion mapped to a test).
Say: plain code checks each of these before the next stage starts; the agents never mark their own
work as done.

**2:45 - 3:45 The PR and the review.** Open the PR: the fix, the new tests, the `autose/ci` check.
Open the review comment: verdict, the four checks, the probes it ran. Say: the reviewer runs in its
own job, sees only the issue, the diff and the code, never the spec or the builder's notes, and it
can't approve or merge.

**3:45 - 4:30 What the reviewer catches.** Open seeded PR #27 (rename that crashes). Show the review
that found the crash with its own probe. Mention: on five seeded PRs it caught all four planted bugs
and approved the clean one, with every setup I tried.

**4:30 - 5:00 What I learned.** Show the ADR list: 13 decisions, three superseded or changed by real
runs (models twice, and the planner's one revision). "The design didn't change; the model behind it
did, twice, and every failed run fixed something in the harness." End on the PR waiting for a
person.
