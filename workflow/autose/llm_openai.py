"""The same agent loop as llm.Agent, for APIs in the OpenAI chat format. Used for DeepSeek
(ADR-013): base URL https://api.deepseek.com, key in DEEPSEEK_API_KEY.

Like the Gemini backend, temporary errors are retried, and an error that won't go away raises
ModelUnavailable, so the stage can move on to the next model in the role's list.
"""
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .budget import Budget
from .llm import MAX_TOOL_OUTPUT, AgentError, ModelUnavailable, QuotaExhausted, Tool, _short

DEEPSEEK_URL = "https://api.deepseek.com"
REQUEST_TIMEOUT_S = 180
RETRIES = 5


def make_client():
    from openai import OpenAI
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise ModelUnavailable("DEEPSEEK_API_KEY is not set")
    # The SDK's own retries are off; call_with_retry below decides, so the log shows each wait.
    return OpenAI(api_key=key, base_url=DEEPSEEK_URL, timeout=REQUEST_TIMEOUT_S, max_retries=0)


def _tool_def(tool: Tool) -> dict:
    schema = dict(tool.schema)
    schema.setdefault("type", "object")
    schema.setdefault("required", list(schema.get("properties", {})))
    return {"type": "function",
            "function": {"name": tool.name, "description": tool.description, "parameters": schema}}


def call_with_retry(fn, *, sleep=time.sleep, **kwargs):
    model = kwargs.get("model", "")
    for attempt in range(RETRIES):
        try:
            return fn(**kwargs)
        except Exception as exc:  # openai.APIStatusError / APIConnectionError / APITimeoutError
            code = getattr(exc, "status_code", None)
            name = type(exc).__name__
            if code == 402:
                raise QuotaExhausted(f"the DeepSeek account has no balance left for {model} "
                                     "(top up at platform.deepseek.com)") from exc
            if code in (401, 403):
                raise AgentError(f"DeepSeek refused the key ({code}); check DEEPSEEK_API_KEY") from exc
            if code == 404:
                raise ModelUnavailable(f"{model} is not offered (404)") from exc
            temporary = code in (429, 500, 502, 503, 504) or "Timeout" in name or "Connection" in name
            if not temporary:
                if code is None:
                    raise  # not an API problem: a real bug, let it show
                raise AgentError(f"DeepSeek API error from {model} ({code}): {str(exc)[:300]}") from exc
            if attempt == RETRIES - 1:
                raise ModelUnavailable(f"{model} kept failing ({code or name})") from exc
            delay = 10.0 * (attempt + 1)
            print(f"[deepseek] {model}: {code or name}, waiting {delay:.0f}s (attempt {attempt + 1})",
                  flush=True)
            sleep(delay)
    raise ModelUnavailable(f"no answer from {model}")


def charge(budget: Budget, model: str, usage) -> None:
    hit = getattr(usage, "prompt_cache_hit_tokens", 0) or 0
    prompt = getattr(usage, "prompt_tokens", 0) or 0
    budget.charge(model, type("U", (), {
        "input_tokens": max(prompt - hit, 0),
        "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "cache_read_input_tokens": hit,
        "cache_creation_input_tokens": 0,
    })())


@dataclass
class OpenAIAgent:
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
        self._tools = [_tool_def(t) for t in self.tools]
        if not self.messages:
            self.messages.append({"role": "system", "content": self.system})

    def send(self, text: str) -> Optional[dict]:
        self.messages.append({"role": "user", "content": text})
        nudged = False
        while True:
            if self.turns >= self.max_turns:
                raise AgentError(f"turn limit reached ({self.max_turns})")
            self.turns += 1
            print(f"[deepseek] {self.model} turn {self.turns}", flush=True)
            response = call_with_retry(self.client.chat.completions.create, model=self.model,
                                       messages=self.messages, tools=self._tools,
                                       max_tokens=8000)
            charge(self.budget, self.model, response.usage)
            choice = response.choices[0]
            message = choice.message
            # Keep everything the API sent (including any reasoning_content, which DeepSeek
            # wants back in the same turn when tools are used).
            self.messages.append(message.model_dump(exclude_none=True))
            if message.content:
                self.log.append({"turn": self.turns, "text": message.content[:2000]})
            calls = message.tool_calls or []

            if not calls:
                if choice.finish_reason == "length":
                    self.messages.append({"role": "user", "content": "Continue."})
                    continue
                if nudged:
                    raise AgentError(f"agent stopped without calling a finishing tool "
                                     f"({choice.finish_reason})")
                nudged = True
                finish = [t.name for t in self.tools if t.stops]
                self.messages.append({"role": "user", "content":
                                      f"You haven't finished. Call {' or '.join(finish)} when done."})
                continue

            stop_input = None
            for call in calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = None
                if not isinstance(args, dict):
                    output, is_error = "Tool arguments must be a JSON object", True
                else:
                    output, is_error = self._run_tool(call.function.name, args)
                self.log.append({"turn": self.turns, "tool": call.function.name,
                                 "input": _short(args), "error": is_error})
                self.messages.append({"role": "tool", "tool_call_id": call.id,
                                      "content": ("ERROR: " if is_error else "") + output})
                tool = self._by_name.get(call.function.name)
                if tool and tool.stops and not is_error:
                    stop_input = args
            if stop_input is not None:
                return stop_input

    def _run_tool(self, name: str, args: dict) -> tuple[str, bool]:
        tool = self._by_name.get(name)
        if tool is None:
            return f"Unknown tool {name}", True
        try:
            output = str(tool.fn(**args))
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"[:MAX_TOOL_OUTPUT], True
        if len(output) > MAX_TOOL_OUTPUT:
            output = output[:MAX_TOOL_OUTPUT] + "\n[... output cut ...]"
        return output, False


def ask_json(*, model: str, system: str, user: str, schema: dict, budget: Budget,
             client: Any = None) -> dict:
    client = client or make_client()
    response = call_with_retry(
        client.chat.completions.create, model=model,
        messages=[{"role": "system", "content": system + "\n\nAnswer with JSON matching this "
                   f"schema, and nothing else:\n{json.dumps(schema)}"},
                  {"role": "user", "content": user}],
        response_format={"type": "json_object"}, max_tokens=4000)
    charge(budget, model, response.usage)
    return json.loads(response.choices[0].message.content or "{}")
