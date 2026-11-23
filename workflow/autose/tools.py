"""The tools agents may call. Each role gets its own subset (ADR-005).

Everything is scoped to the repository checkout. Commands run with secrets removed from the
environment (ADR-009), so code written by an agent can't read the API key while tests run.
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

from .config import Config
from .llm import Tool

SKIP_DIRS = {".git", "__pycache__", ".venv", ".mypy_cache", ".pytest_cache", "node_modules"}
SECRET_PATTERN = re.compile(r"(_API_KEY|_TOKEN|_SECRET|PASSWORD)$|^GH_|^GITHUB_TOKEN$")


def clean_env() -> dict[str, str]:
    """A copy of the environment without anything that looks like a secret."""
    return {k: v for k, v in os.environ.items() if not SECRET_PATTERN.search(k)}


def run_command(cmd: str, cwd: Path, timeout: int) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, shell=True, cwd=cwd, env=clean_env(), timeout=timeout,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              encoding="utf-8", errors="replace")
        return proc.returncode, proc.stdout
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        return 124, out + f"\n[timed out after {timeout}s]"


def tail(text: str, limit: int = 8000) -> str:
    return text if len(text) <= limit else "[...]\n" + text[-limit:]


def path_allowed(rel: str, allowed: list[str], denied: list[str]) -> bool:
    rel = rel.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    if ".." in rel.split("/"):
        return False
    if any(rel == d.rstrip("/") or rel.startswith(d) for d in denied):
        return False
    return any(rel.startswith(a) for a in allowed)


class Workspace:
    def __init__(self, config: Config, base_ref: str, artifacts: Path):
        self.config = config
        self.root = config.repo_root
        self.base_ref = base_ref
        self.artifacts = artifacts
        self.timeout = config.limit("command_timeout_s")
        self.submitted: dict = {}
        self.allowed_artifacts: set[str] = set()

    # --- helpers -----------------------------------------------------------------

    def _resolve(self, path: str) -> Path:
        target = (self.root / path).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("path is outside the repository")
        if ".git" in target.relative_to(self.root).parts:
            raise ValueError("the .git directory is off limits")
        return target

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    # --- read tools ---------------------------------------------------------------

    def read_file(self, path: str, start_line: int = 1, end_line: int = 0) -> str:
        target = self._resolve(path)
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        end = end_line if end_line > 0 else len(lines)
        start = max(start_line, 1)
        chunk = lines[start - 1:end]
        return "\n".join(f"{n:5d}  {line}" for n, line in enumerate(chunk, start)) or "(empty)"

    def list_files(self, directory: str = ".") -> str:
        base = self._resolve(directory)
        found = []
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in sorted(filenames):
                found.append(self._rel(Path(dirpath) / name))
                if len(found) >= 400:
                    return "\n".join(found) + "\n[... more files ...]"
        return "\n".join(found)

    def search_code(self, pattern: str, directory: str = ".") -> str:
        regex = re.compile(pattern)
        hits = []
        for rel in self.list_files(directory).splitlines():
            if rel.startswith("[") or not rel.endswith((".py", ".md", ".rst", ".txt", ".toml", ".ini", ".yml")):
                continue
            text = (self.root / rel).read_text(encoding="utf-8", errors="replace")
            for n, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    hits.append(f"{rel}:{n}: {line.strip()[:200]}")
                    if len(hits) >= 60:
                        return "\n".join(hits) + "\n[... more matches ...]"
        return "\n".join(hits) or "no matches"

    def git_diff(self) -> str:
        subprocess.run(["git", "add", "-N", "."], cwd=self.root, capture_output=True)
        out = subprocess.run(["git", "diff", self.base_ref], cwd=self.root,
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
        return out.stdout or "(no changes)"

    # --- write tools (builder only) --------------------------------------------------

    def _check_writable(self, path: str) -> Path:
        target = self._resolve(path)
        if not path_allowed(self._rel(target), self.config.allowed_paths, self.config.denied_paths):
            raise PermissionError(f"{self._rel(target)} is not in the allowed edit paths "
                                  f"{self.config.allowed_paths}")
        return target

    def write_file(self, path: str, content: str) -> str:
        target = self._check_writable(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"wrote {self._rel(target)} ({len(content.splitlines())} lines)"

    def replace_in_file(self, path: str, old: str, new: str) -> str:
        target = self._check_writable(path)
        text = target.read_text(encoding="utf-8")
        count = text.count(old)
        if count != 1:
            raise ValueError(f"`old` must appear exactly once in {path}, found {count} times")
        target.write_text(text.replace(old, new), encoding="utf-8")
        return f"updated {self._rel(target)}"

    # --- run tools -----------------------------------------------------------------

    def run_build(self) -> str:
        code, out = run_command(self.config["build_cmd"], self.root, self.timeout)
        return f"exit code {code}\n{tail(out)}"

    def run_tests(self, target: str = "") -> str:
        cmd = self.config["test_cmd"]
        if target:
            if not re.fullmatch(r"[\w./:\[\]-]+", target):
                raise ValueError("target must be a test path or node id")
            cmd = cmd[: -len(" tests")] + " " + target if cmd.endswith(" tests") else f"{cmd} {target}"
        code, out = run_command(cmd, self.root, self.timeout)
        return f"command: {cmd}\nexit code {code}\n{tail(out)}"

    def run_python(self, code: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            script = f.name
        try:
            rc, out = run_command(f'"{sys.executable}" "{script}"', self.root, 60)
        finally:
            os.unlink(script)
        return f"exit code {rc}\n{tail(out)}"

    # --- artifacts and finishing tools -------------------------------------------------

    def write_artifact(self, name: str, content: str) -> str:
        if name not in self.allowed_artifacts:
            raise ValueError(f"you can only write {sorted(self.allowed_artifacts)}")
        (self.artifacts / name).write_text(content, encoding="utf-8")
        self.submitted[name] = content
        return f"saved {name}"

    def submit(self, key: str) -> Callable[..., str]:
        def _submit(**kwargs) -> str:
            self.submitted[key] = kwargs
            return "submitted"
        return _submit


# --- tool sets per role --------------------------------------------------------------

def _t(name, desc, props, fn, stops=False, required=None):
    schema = {"type": "object", "properties": props}
    schema["required"] = required if required is not None else list(props)
    return Tool(name, desc, schema, fn, stops)


S = {"type": "string"}
I = {"type": "integer"}


def read_tools(ws: Workspace) -> list[Tool]:
    return [
        _t("read_file", "Read a file from the repository, with line numbers. end_line 0 means to the end.",
           {"path": S, "start_line": I, "end_line": I}, ws.read_file),
        _t("list_files", "List files under a directory of the repository ('.' for all).",
           {"directory": S}, ws.list_files),
        _t("search_code", "Search repository files with a Python regular expression.",
           {"pattern": S, "directory": S}, ws.search_code),
    ]


def planner_tools(ws: Workspace, artifact: str) -> list[Tool]:
    ws.allowed_artifacts = {artifact}
    return read_tools(ws) + [
        _t("write_artifact", f"Save {artifact}. Call this once when it is complete.",
           {"name": S, "content": S}, ws.write_artifact, stops=True),
    ]


def builder_tools(ws: Workspace) -> list[Tool]:
    mapping = {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["ac", "test"],
        "properties": {"ac": S, "test": S}}}
    return read_tools(ws) + [
        _t("write_file", "Create or overwrite a file (allowed paths only).",
           {"path": S, "content": S}, ws.write_file),
        _t("replace_in_file", "Replace a piece of text that appears exactly once in a file.",
           {"path": S, "old": S, "new": S}, ws.replace_in_file),
        _t("run_build", "Run the repository build command.", {}, ws.run_build),
        _t("run_tests", "Run the test suite, or one test file / node id if target is given ('' for all).",
           {"target": S}, ws.run_tests),
        _t("git_diff", "Show your changes so far compared with the starting commit.", {}, ws.git_diff),
        _t("submit_work", "Finish: map every acceptance criterion (AC-1, AC-2, ...) to the pytest "
           "node id that tests it, and summarise the change in one or two sentences.",
           {"ac_mapping": mapping, "summary": S}, ws.submit("work"), stops=True),
    ]


def reviewer_tools(ws: Workspace) -> list[Tool]:
    finding = {"type": "object", "additionalProperties": False,
               "required": ["ok", "finding"], "properties": {"ok": {"type": "boolean"}, "finding": S}}
    defect = {"type": "object", "additionalProperties": False,
              "required": ["file", "line", "description", "blocking"],
              "properties": {"file": S, "line": I, "description": S, "blocking": {"type": "boolean"}}}
    return read_tools(ws) + [
        _t("git_diff", "Show the pull request diff.", {}, ws.git_diff),
        _t("run_tests", "Run the test suite, or one test file / node id if target is given ('' for all).",
           {"target": S}, ws.run_tests),
        _t("run_python", "Run a short Python script from the repository root, e.g. to probe an "
           "edge case. Nothing it changes is pushed.", {"code": S}, ws.run_python),
        _t("submit_review", "Finish the review.", {
            "verdict": {"type": "string", "enum": ["APPROVE", "REQUEST_CHANGES"]},
            "routing_target": {"type": "string", "enum": ["implementation", "design", "none"]},
            "summary": S,
            "issue_fidelity": finding, "api_invariants": finding,
            "edge_cases": finding, "test_adequacy": finding,
            "tests_command": S, "tests_exit_code": I,
            "defects": {"type": "array", "items": defect},
        }, ws.submit("review"), stops=True),
    ]
