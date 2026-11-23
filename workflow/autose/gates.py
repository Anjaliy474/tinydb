"""Stage gates (ADR-007). Plain code decides pass or fail, not the agents.

Only Stage 1 asks a model anything (is each acceptance criterion testable?), and even there the
format checks below run first and the final decision is made here.
"""
import ast
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .config import Config
from .tools import path_allowed, run_command

VAGUE_WORDS = ["fast", "faster", "quickly", "better", "easy", "easily", "user-friendly", "robust",
               "efficient", "appropriate", "appropriately", "properly", "seamless", "seamlessly",
               "nice", "nicely", "clean", "reasonable", "intuitive", "etc", "correctly",
               "as expected", "as before", "works", "normally"]


@dataclass
class GateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)

    def fail(self, reason: str) -> None:
        self.passed = False
        self.reasons.append(reason)


# --- shared helpers --------------------------------------------------------------------

def front_matter(text: str) -> dict[str, str]:
    match = re.match(r"\s*---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not match:
        return {}
    out = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            out[key.strip()] = value.split("#", 1)[0].strip()
    return out


def section(text: str, title: str) -> str:
    match = re.search(rf"^##\s+{re.escape(title)}\s*$(.*?)(?=^##\s|\Z)", text, re.S | re.M | re.I)
    return match.group(1) if match else ""


def acceptance_criteria(spec: str) -> dict[str, str]:
    body = section(spec, "Acceptance criteria")
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"^\s*-\s*\**(AC-\d+)\**\s*:\s*(.+)$", body, re.M)}


def add_diagnostics(path: Path, result: GateResult) -> None:
    """Append the gate's reasons to the artifact so a person can see why the stage stopped."""
    lines = ["", "## Gate Failure Diagnostics", ""] + [f"- {r}" for r in result.reasons]
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# --- Stage 1: spec.md --------------------------------------------------------------------

JUDGE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["criteria"],
    "properties": {"criteria": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "testable", "reason"],
        "properties": {"id": {"type": "string"}, "testable": {"type": "boolean"},
                       "reason": {"type": "string"}}}}},
}


def gate_spec(spec: str, judge: Optional[Callable[[dict[str, str]], dict]] = None) -> GateResult:
    result = GateResult(True)
    meta = front_matter(spec)
    if meta.get("stage") != "1":
        result.fail("front matter must contain `stage: 1`")
    if meta.get("status") == "blocked":
        result.fail("the planner marked the spec as blocked (see Notes)")
    criteria = acceptance_criteria(spec)
    if len(criteria) < 2:
        result.fail(f"need at least 2 acceptance criteria, found {len(criteria)}")
    for ac_id, text in criteria.items():
        lowered = text.lower()
        if not all(w in lowered for w in ("given", "when", "then")):
            result.fail(f"{ac_id} is not written as Given / When / Then")
        vague = [w for w in VAGUE_WORDS if re.search(rf"\b{re.escape(w)}\b", lowered)]
        if vague:
            result.fail(f"{ac_id} uses vague words: {', '.join(vague)}")
    result.data["criteria"] = criteria
    if result.passed and judge is not None:
        verdict = judge(criteria)
        result.data["judge"] = verdict
        seen = {c["id"]: c for c in verdict.get("criteria", [])}
        for ac_id in criteria:
            item = seen.get(ac_id)
            if item is None:
                result.fail(f"testability check gave no answer for {ac_id}")
            elif not item["testable"]:
                result.fail(f"{ac_id} judged not testable: {item['reason']}")
    return result


# --- Stage 2: design.md ------------------------------------------------------------------

CHANGE_LINE = re.compile(r"`([^`]+)`\s*(\[NEW\])?\s*::\s*`([^`]+)`\s*(\[NEW\])?")


def defined_symbols(source: str) -> set[str]:
    names = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(f"{node.name}.{item.name}")
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def gate_design(design: str, config: Config) -> GateResult:
    result = GateResult(True)
    if front_matter(design).get("stage") != "2":
        result.fail("front matter must contain `stage: 2`")
    changes = [m for m in (CHANGE_LINE.search(line) for line in
                           section(design, "Changes").splitlines()) if m]
    if not changes:
        result.fail("no lines of the form `path` :: `symbol` under ## Changes")
    for m in changes:
        path, new_file, symbol, new_symbol = m.group(1), m.group(2), m.group(3), m.group(4)
        if not path_allowed(path, config.allowed_paths, config.denied_paths):
            result.fail(f"{path} is outside the allowed edit paths")
            continue
        file = config.repo_root / path
        if new_file:
            if file.exists():
                result.fail(f"{path} is marked [NEW] but already exists")
            continue
        if not file.exists():
            result.fail(f"{path} does not exist (mark it [NEW] if it is a new file)")
            continue
        if new_symbol or not path.endswith(".py"):
            continue
        if symbol.rstrip("()") not in defined_symbols(file.read_text(encoding="utf-8")):
            result.fail(f"`{symbol}` is not defined in {path} (mark it [NEW] if it is new)")
    if "tests/" not in section(design, "Tests"):
        result.fail("## Tests must name at least one file under tests/")
    result.data["files"] = sorted({m.group(1) for m in changes})
    return result


# --- Stage 3: diff.patch -----------------------------------------------------------------

def changed_files(repo: Path, base_ref: str) -> list[str]:
    subprocess.run(["git", "add", "-N", "."], cwd=repo, capture_output=True)
    out = subprocess.run(["git", "diff", "--name-only", base_ref], cwd=repo,
                         capture_output=True, text=True)
    return [line for line in out.stdout.splitlines() if line]


def make_patch(repo: Path, base_ref: str) -> str:
    subprocess.run(["git", "add", "-N", "."], cwd=repo, capture_output=True)
    out = subprocess.run(["git", "diff", "--binary", base_ref], cwd=repo,
                         capture_output=True, text=True, encoding="utf-8")
    return out.stdout


def gate_implementation(config: Config, base_ref: str) -> GateResult:
    result = GateResult(True)
    repo = config.repo_root
    files = changed_files(repo, base_ref)
    result.data["files"] = files
    if not files:
        result.fail("the diff is empty")
        return result
    for f in files:
        if not path_allowed(f, config.allowed_paths, config.denied_paths):
            result.fail(f"{f} is outside the allowed edit paths")
    patch = make_patch(repo, base_ref)
    result.data["patch"] = patch
    with tempfile.TemporaryDirectory() as tmp:
        wt = Path(tmp) / "wt"
        subprocess.run(["git", "worktree", "add", "--detach", str(wt), base_ref],
                       cwd=repo, capture_output=True)
        try:
            (Path(tmp) / "p.diff").write_text(patch, encoding="utf-8")
            check = subprocess.run(["git", "apply", "--check", str(Path(tmp) / "p.diff")],
                                   cwd=wt, capture_output=True, text=True)
            if check.returncode != 0:
                result.fail(f"git apply --check failed: {check.stderr.strip()[:500]}")
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(wt)],
                           cwd=repo, capture_output=True)
    code, out = run_command(config["build_cmd"], repo, config.limit("command_timeout_s"))
    if code != 0:
        result.fail(f"build failed (exit {code}): {out.strip()[-1500:]}")
    return result


# --- Stage 4: test_report.md ---------------------------------------------------------------

def run_junit(config: Config) -> tuple[int, str, dict]:
    """Run the test command with a JUnit report. Returns (exit code, output, results)."""
    with tempfile.TemporaryDirectory() as tmp:
        xml_path = Path(tmp) / "junit.xml"
        cmd = f'{config["test_cmd"]} --junitxml="{xml_path}"'
        code, out = run_command(cmd, config.repo_root, config.limit("command_timeout_s"))
        cases: dict[tuple[str, str], str] = {}
        skipped = 0
        if xml_path.exists():
            for case in ET.parse(xml_path).iter("testcase"):
                status = "passed"
                if case.find("failure") is not None or case.find("error") is not None:
                    status = "failed"
                elif case.find("skipped") is not None:
                    status = "skipped"
                    skipped += 1
                cases[(case.get("classname", ""), case.get("name", ""))] = status
    return code, out, {"cases": cases, "skipped": skipped}


def _node_matches(node_id: str, classname: str, name: str) -> bool:
    parts = node_id.split("::")
    if len(parts) < 2:
        return False
    module = parts[0].replace("\\", "/").removesuffix(".py").replace("/", ".")
    expected_class = ".".join([module] + parts[1:-1])
    func = parts[-1]
    return classname == expected_class and (name == func or name.startswith(func + "["))


def failure_signature(output: str) -> str:
    failed = sorted(set(re.findall(r"^(?:FAILED|ERROR) (\S+)", output, re.M)))
    return "|".join(failed) or output.strip()[-300:]


def gate_tests(config: Config, criteria: dict[str, str], mapping: list[dict],
               files: list[str], baseline_skipped: int) -> GateResult:
    result = GateResult(True)
    code, out, junit = run_junit(config)
    result.data.update(exit_code=code, output=out, junit=junit,
                       signature=failure_signature(out) if code else "")
    if code != 0:
        result.fail(f"test command exited with {code}")
    if junit["skipped"] > baseline_skipped:
        result.fail(f"{junit['skipped']} skipped tests, there were {baseline_skipped} before")
    mapped = {m["ac"]: m["test"] for m in mapping}
    changed_tests = {f for f in files if f.startswith("tests/")}
    for ac_id in criteria:
        node = mapped.get(ac_id)
        if not node:
            result.fail(f"{ac_id} has no test mapped to it")
            continue
        if node.split("::")[0].replace("\\", "/") not in changed_tests:
            result.fail(f"{ac_id} maps to {node}, which is not in a test file changed by this diff")
        statuses = [s for (cls, name), s in junit["cases"].items() if _node_matches(node, cls, name)]
        if not statuses:
            result.fail(f"{ac_id} maps to {node}, which did not run")
        elif any(s != "passed" for s in statuses):
            result.fail(f"{ac_id} maps to {node}, which did not pass")
    return result


# --- Stage 5: the pull request -----------------------------------------------------------------

def gate_release(pr: dict, config: Config, ci_passed: Optional[bool]) -> GateResult:
    result = GateResult(True)
    if pr.get("state") != "OPEN":
        result.fail(f"PR state is {pr.get('state')}, expected OPEN")
    if pr.get("baseRefName") != config["base_branch"]:
        result.fail(f"PR targets {pr.get('baseRefName')}, expected {config['base_branch']}")
    if not str(pr.get("headRefName", "")).startswith("autose/issue-"):
        result.fail("PR head branch is not an autose/issue-N branch")
    repo = (pr.get("headRepository") or {}).get("nameWithOwner") or pr.get("repo")
    if repo and repo != config["fork_repo"]:
        result.fail(f"PR is in {repo}, expected {config['fork_repo']}")
    if ci_passed is False:
        result.fail("CI failed on the PR head")
    return result


# --- Stage 6: review.md -------------------------------------------------------------------

DIMENSIONS = ("issue_fidelity", "api_invariants", "edge_cases", "test_adequacy")


def gate_review(review: dict, round_no: int, ran_tests: bool) -> GateResult:
    result = GateResult(True)
    verdict, route = review.get("verdict"), review.get("routing_target")
    if round_no > 2:
        result.fail("review round is above 2")
    if not ran_tests:
        result.fail("the reviewer never ran the test suite")
    if not str(review.get("tests_command", "")).strip():
        result.fail("no test command recorded")
    for dim in DIMENSIONS:
        item = review.get(dim) or {}
        if not str(item.get("finding", "")).strip():
            result.fail(f"no finding for {dim}")
    blocking = [d for d in review.get("defects", []) if d.get("blocking")]
    if verdict == "APPROVE":
        if blocking:
            result.fail("APPROVE together with blocking defects")
        if route != "none":
            result.fail("APPROVE must have routing_target none")
    elif verdict == "REQUEST_CHANGES":
        if not blocking:
            result.fail("REQUEST_CHANGES needs at least one blocking defect")
        if any(not d.get("file") or int(d.get("line", 0)) <= 0 for d in blocking):
            result.fail("every blocking defect needs a file and a line")
        if route not in ("implementation", "design"):
            result.fail("REQUEST_CHANGES needs routing_target implementation or design")
    else:
        result.fail(f"unknown verdict {verdict!r}")
    return result
