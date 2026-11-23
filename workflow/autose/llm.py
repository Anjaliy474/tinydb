"""A small agent loop on the Anthropic Messages API, with our own tools.

We run the loop ourselves (instead of an off-the-shelf coding agent) so each role gets only the
tools we hand it (ADR-005), and so every call is charged to the stage's budget (ADR-009).
"""
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .budget import Budget

MAX_TOOL_OUTPUT = 20_000
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AgentError(RuntimeError):
    pass


def make_client():
    import anthropic
    return anthropic.Anthropic(max_retries=4, timeout=600)


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    fn: Callable[..., str]
    stops: bool = False  # calling this tool ends the agent's turn (e.g. submit_review)

    def definition(self) -> dict:
        schema = dict(self.schema)
        schema.setdefault("type", "object")
        schema.setdefault("additionalProperties", False)
        schema.setdefault("required", list(schema.get("properties", {})))
        return {"name": self.name, "description": self.description,
                "input_schema": schema, "strict": True}


@dataclass
class Agent:
    model: str
    system: str
    tools: list[Tool]
    budget: Budget
    max_turns: int
    effort: str = "medium"
    client: Any = None
    messages: list = field(default_factory=list)
    turns: int = 0
    log: list = field(default_factory=list)

    def __post_init__(self):
        self.client = self.client or make_client()
        self._by_name = {t.name: t for t in self.tools}

    def _create(self):
        kwargs = dict(
            model=self.model,
            max_tokens=16000,
            system=[{"type": "text", "text": self.system,
                     "cache_control": {"type": "ephemeral"}}],
            tools=[t.definition() for t in self.tools],
            messages=self.messages,
            output_config={"effort": self.effort},
            cache_control={"type": "ephemeral"},
        )
        if not self.model.startswith("claude-haiku"):
            # If a request is declined by a safety classifier, let the API retry it on a
            # fallback model instead of failing the stage.
            kwargs.update(betas=[FALLBACK_BETA], fallbacks="default")
        return self.client.beta.messages.create(**kwargs)

    def send(self, text: str) -> Optional[dict]:
        """Add a user message and run until a stopping tool is called.

        Returns the input of the stopping tool call, or raises AgentError.
        """
        self.messages.append({"role": "user", "content": text})
        nudged = False
        while True:
            if self.turns >= self.max_turns:
                raise AgentError(f"turn limit reached ({self.max_turns})")
            self.turns += 1
            response = self._create()
            self.budget.charge(self.model, response.usage)
            if response.stop_reason == "refusal":
                raise AgentError(f"model refused: {getattr(response, 'stop_details', None)}")
            self.messages.append({"role": "assistant", "content": response.content})

            calls = [b for b in response.content if getattr(b, "type", "") == "tool_use"]
            texts = [b.text for b in response.content if getattr(b, "type", "") == "text"]
            if texts:
                self.log.append({"turn": self.turns, "text": "\n".join(texts)[:2000]})

            if not calls:
                if response.stop_reason == "max_tokens":
                    self.messages.append({"role": "user", "content": "Continue."})
                    continue
                if nudged:
                    raise AgentError("agent stopped without calling a finishing tool")
                nudged = True
                finish = [t.name for t in self.tools if t.stops]
                self.messages.append({"role": "user", "content":
                                      f"You haven't finished. Call {' or '.join(finish)} when done."})
                continue

            results, stop_input = [], None
            for call in calls:
                output, is_error = self._run_tool(call.name, call.input)
                self.log.append({"turn": self.turns, "tool": call.name,
                                 "input": _short(call.input), "error": is_error})
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": output, "is_error": is_error})
                tool = self._by_name.get(call.name)
                if tool and tool.stops and not is_error:
                    stop_input = dict(call.input)
            self.messages.append({"role": "user", "content": results})
            if stop_input is not None:
                return stop_input

    def _run_tool(self, name: str, args: Any) -> tuple[str, bool]:
        tool = self._by_name.get(name)
        if tool is None:
            return f"Unknown tool {name}", True
        if not isinstance(args, dict):
            return "Tool input must be an object", True
        try:
            output = tool.fn(**args)
        except Exception as exc:  # tool errors go back to the model, not up the stack
            return f"{type(exc).__name__}: {exc}"[:MAX_TOOL_OUTPUT], True
        output = str(output)
        if len(output) > MAX_TOOL_OUTPUT:
            output = output[:MAX_TOOL_OUTPUT] + "\n[... output cut ...]"
        return output, False


def ask_json(*, model: str, system: str, user: str, schema: dict, budget: Budget,
             client: Any = None) -> dict:
    """One call that must answer in a JSON schema (used for the Stage 1 testability check)."""
    client = client or make_client()
    response = client.messages.create(
        model=model,
        max_tokens=4000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "low",
                       "format": {"type": "json_schema", "schema": schema}},
    )
    budget.charge(model, response.usage)
    if response.stop_reason == "refusal":
        raise AgentError("judge refused")
    text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
    return json.loads(text)


def make_agent(**kwargs):
    """Pick the agent loop for the model's provider (ADR-011): gemini-* or claude-*."""
    if kwargs["model"].startswith("gemini"):
        from .llm_gemini import GeminiAgent
        return GeminiAgent(**kwargs)
    return Agent(**kwargs)


def ask_json_any(**kwargs) -> dict:
    if kwargs["model"].startswith("gemini"):
        from .llm_gemini import ask_json as gemini_ask_json
        return gemini_ask_json(**kwargs)
    return ask_json(**kwargs)


def _short(value: Any) -> str:
    text = json.dumps(value, default=str)
    return text if len(text) < 300 else text[:300] + "..."
