"""The same agent loop as llm.Agent, on the Gemini API (google-genai).

Added after ADR-011: there is no paid Anthropic access for this project, so the default models
are Gemini models on the free tier. The free tier has small per-minute and per-day limits, so
every call waits and retries on HTTP 429 instead of failing the stage straight away.
"""
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .budget import Budget
from .llm import MAX_TOOL_OUTPUT, AgentError, ModelUnavailable, QuotaExhausted, Tool, _short

MAX_WAIT_S = 600       # give up on one call after waiting this long in total
REQUEST_TIMEOUT_MS = 120_000
RETRIES = 8


def make_client():
    from google import genai
    from google.genai import types
    # A request that hangs fails after 2 minutes and is retried, instead of blocking the job
    # until GitHub cancels it (that is what happened on the first run).
    return genai.Client(http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))  # reads GEMINI_API_KEY


def _schema(tool: Tool) -> dict:
    """Gemini doesn't need (or always accept) the strict-mode extras Claude uses."""
    def clean(node):
        if isinstance(node, dict):
            return {k: clean(v) for k, v in node.items() if k not in ("additionalProperties", "strict")}
        if isinstance(node, list):
            return [clean(v) for v in node]
        return node
    schema = clean(dict(tool.schema))
    schema.setdefault("type", "object")
    schema.setdefault("required", list(schema.get("properties", {})))
    return schema


# Spacing between calls, so a burst of tool calls doesn't run into the per-minute limit.
MIN_INTERVAL_S = float(os.environ.get("AUTOSE_GEMINI_MIN_INTERVAL", "4"))
_last_call: dict[str, float] = {}


def _retry_delay(exc: Exception) -> float:
    match = re.search(r"retry(?:Delay| in)[\"': ]+([\d.]+)s", str(exc), re.I)
    return float(match.group(1)) + 1 if match else 30.0


def is_daily_quota(exc: Exception) -> bool:
    text = str(exc)
    return bool(re.search(r"PerDay|per[ _]day|RequestsPerDay|daily", text, re.I))


def _pace(model: str, sleep) -> None:
    last = _last_call.get(model)
    if last is not None:
        gap = MIN_INTERVAL_S - (time.monotonic() - last)
        if gap > 0:
            sleep(gap)
    _last_call[model] = time.monotonic()


TEMPORARY = (429, 500, 502, 503, 504)


def call_with_retry(fn, *args, sleep=time.sleep, **kwargs):
    """Call Gemini, waiting out temporary errors. Anything that still fails becomes an
    AgentError, so the stage ends cleanly and writes its report instead of crashing."""
    waited = 0.0
    model = kwargs.get("model", "")
    for attempt in range(RETRIES):
        _pace(model, sleep)
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # google.genai.errors.APIError, but keep this import-free
            code = getattr(exc, "code", None)
            if code == 429 and is_daily_quota(exc):
                print(f"[gemini] {model}: daily free quota used up", flush=True)
                raise QuotaExhausted(
                    f"the free daily quota for {model} is used up; it resets at midnight "
                    "Pacific time (13:30 IST). Restart with /autose after that, or switch this "
                    "role to another model in .autose.yml") from exc
            timed_out = "timeout" in type(exc).__name__.lower() or "timed out" in str(exc).lower()
            if code is None and not timed_out:
                raise  # not an API problem: a real bug, let it show
            if timed_out:
                code = "timeout"
            delay = min(_retry_delay(exc) if code == 429 else 15.0 * (attempt + 1),
                        MAX_WAIT_S - waited)
            if code == 404:
                raise ModelUnavailable(f"{model} is not offered to this key (404)") from exc
            if code in TEMPORARY and (attempt == RETRIES - 1 or delay <= 0):
                raise ModelUnavailable(f"{model} kept failing ({code}) after {attempt + 1} tries") from exc
            if code not in TEMPORARY and code != "timeout":
                raise AgentError(f"Gemini API error from {model} ({code}): {str(exc)[:300]}") from exc
            if code == "timeout" and attempt == RETRIES - 1:
                raise ModelUnavailable(f"{model} timed out {RETRIES} times") from exc
            print(f"[gemini] {model}: {code}, waiting {delay:.0f}s (attempt {attempt + 1})", flush=True)
            sleep(delay)
            waited += delay
    raise AgentError(f"Gemini API: no answer from {model}")


def charge(budget: Budget, model: str, response) -> None:
    meta = getattr(response, "usage_metadata", None)
    budget.charge(model, type("U", (), {
        "input_tokens": (getattr(meta, "prompt_token_count", 0) or 0)
        - (getattr(meta, "cached_content_token_count", 0) or 0),
        "output_tokens": (getattr(meta, "candidates_token_count", 0) or 0)
        + (getattr(meta, "thoughts_token_count", 0) or 0),
        "cache_read_input_tokens": getattr(meta, "cached_content_token_count", 0) or 0,
        "cache_creation_input_tokens": 0,
    })())


@dataclass
class GeminiAgent:
    model: str
    system: str
    tools: list[Tool]
    budget: Budget
    max_turns: int
    effort: str = "medium"
    client: Any = None
    contents: list = field(default_factory=list)
    turns: int = 0
    log: list = field(default_factory=list)

    def __post_init__(self):
        from google.genai import types
        self._types = types
        self.client = self.client or make_client()
        self._by_name = {t.name: t for t in self.tools}
        self._config = types.GenerateContentConfig(
            system_instruction=self.system,
            tools=[types.Tool(function_declarations=[
                types.FunctionDeclaration(name=t.name, description=t.description,
                                          parameters_json_schema=_schema(t))
                for t in self.tools])],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            max_output_tokens=16000,
        )

    def _add_user(self, parts: list) -> None:
        # Keep turns alternating: add to the last user turn if there is one.
        if self.contents and self.contents[-1].role == "user":
            self.contents[-1].parts.extend(parts)
        else:
            self.contents.append(self._types.Content(role="user", parts=parts))

    def send(self, text: str) -> Optional[dict]:
        T = self._types
        self._add_user([T.Part(text=text)])
        nudged = False
        while True:
            if self.turns >= self.max_turns:
                raise AgentError(f"turn limit reached ({self.max_turns})")
            self.turns += 1
            print(f"[gemini] {self.model} turn {self.turns}", flush=True)
            response = call_with_retry(self.client.models.generate_content, model=self.model,
                                       contents=self.contents, config=self._config)
            charge(self.budget, self.model, response)
            candidate = (response.candidates or [None])[0]
            if candidate is None or candidate.content is None:
                reason = getattr(candidate, "finish_reason", None) if candidate else "no candidate"
                raise AgentError(f"model returned nothing ({reason})")
            self.contents.append(candidate.content)  # keeps thought signatures for the next turn
            parts = candidate.content.parts or []
            calls = [p.function_call for p in parts if p.function_call]
            texts = [p.text for p in parts if p.text and not p.thought]
            if texts:
                self.log.append({"turn": self.turns, "text": "\n".join(texts)[:2000]})

            if not calls:
                if str(candidate.finish_reason).endswith("MAX_TOKENS"):
                    self._add_user([T.Part(text="Continue.")])
                    continue
                if nudged:
                    raise AgentError(f"agent stopped without calling a finishing tool "
                                     f"({candidate.finish_reason})")
                nudged = True
                finish = [t.name for t in self.tools if t.stops]
                self._add_user([T.Part(text=f"You haven't finished. Call {' or '.join(finish)} when done.")])
                continue

            results, stop_input = [], None
            for call in calls:
                args = dict(call.args or {})
                output, is_error = self._run_tool(call.name, args)
                self.log.append({"turn": self.turns, "tool": call.name, "input": _short(args),
                                 "error": is_error})
                key = "error" if is_error else "result"
                results.append(T.Part.from_function_response(name=call.name, response={key: output}))
                tool = self._by_name.get(call.name)
                if tool and tool.stops and not is_error:
                    stop_input = args
            self._add_user(results)
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
    from google.genai import types
    client = client or make_client()
    clean = _schema(Tool("x", "", schema, lambda: ""))
    response = call_with_retry(
        client.models.generate_content, model=model, contents=user,
        config=types.GenerateContentConfig(system_instruction=system,
                                           response_mime_type="application/json",
                                           response_json_schema=clean, max_output_tokens=4000))
    charge(budget, model, response)
    return json.loads(response.text)
