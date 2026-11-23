"""Loads .autose.yml and knows where things live during a run."""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@dataclass
class Config:
    raw: dict[str, Any]
    repo_root: Path

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def limit(self, name: str) -> int:
        return int(self.raw["limits"][name])

    def models(self, role: str) -> list[str]:
        """The role's models in order of preference. A role can list several so a run can move
        on when one model's free quota is gone (ADR-011). An env var (used by the experiments)
        pins a single model."""
        pinned = os.environ.get(f"AUTOSE_{role.upper()}_MODEL")
        if pinned:
            return [pinned]
        value = self.raw["models"][role]
        return [value] if isinstance(value, str) else list(value)

    def model(self, role: str) -> str:
        return self.models(role)[0]

    @property
    def allowed_paths(self) -> list[str]:
        return list(self.raw["allowed_edit_paths"])

    @property
    def denied_paths(self) -> list[str]:
        return list(self.raw["denied_edit_paths"])


def load(repo_root: str | os.PathLike | None = None) -> Config:
    """Load the config. In Actions, AUTOSE_CONFIG points at the copy from the trusted harness
    checkout (master), so a PR can't change the rules it is checked against."""
    root = Path(repo_root or os.environ.get("AUTOSE_REPO", ".")).resolve()
    path = Path(os.environ.get("AUTOSE_CONFIG") or root / ".autose.yml")
    with open(path, encoding="utf-8") as f:
        return Config(yaml.safe_load(f), root)


def prompt(name: str, **values: str) -> str:
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def artifacts_dir() -> Path:
    path = Path(os.environ.get("AUTOSE_ARTIFACTS", "autose-artifacts")).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path
