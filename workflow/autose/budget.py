"""Token and cost accounting with hard caps (ADR-009).

Each job gets its own dollar cap. Usage is written to run_state.json so the finalize step and the
report can add it up across jobs.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

# USD per 1M tokens: (input, output, cache read, cache write).
# Source: Anthropic pricing page (Haiku price is for prompts up to 100K tokens).
PRICES = {
    "claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
}


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    usd_cap: float
    token_cap: int
    stage: str
    usd: float = 0.0
    tokens: int = 0
    calls: list[dict] = field(default_factory=list)

    def charge(self, model: str, usage) -> None:
        inp = getattr(usage, "input_tokens", 0) or 0
        out = getattr(usage, "output_tokens", 0) or 0
        c_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        c_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        p_in, p_out, p_read, p_write = PRICES.get(model, PRICES["claude-opus-5-5"])
        cost = (inp * p_in + out * p_out + c_read * p_read + c_write * p_write) / 1_000_000
        self.usd += cost
        self.tokens += inp + out + c_read + c_write
        self.calls.append({"model": model, "input": inp, "output": out,
                           "cache_read": c_read, "cache_write": c_write,
                           "usd": round(cost, 5)})
        if self.usd > self.usd_cap:
            raise BudgetExceeded(f"{self.stage}: spent ${self.usd:.2f}, cap is ${self.usd_cap:.2f}")
        if self.tokens > self.token_cap:
            raise BudgetExceeded(f"{self.stage}: used {self.tokens} tokens, cap is {self.token_cap}")

    def summary(self) -> dict:
        return {"stage": self.stage, "usd": round(self.usd, 4), "tokens": self.tokens,
                "calls": len(self.calls), "detail": self.calls}

    def save(self, directory: Path) -> None:
        path = directory / "run_state.json"
        state = json.loads(path.read_text()) if path.exists() else {"stages": []}
        state["stages"].append(self.summary())
        state["total_usd"] = round(sum(s["usd"] for s in state["stages"]), 4)
        state["total_tokens"] = sum(s["tokens"] for s in state["stages"])
        path.write_text(json.dumps(state, indent=2))
