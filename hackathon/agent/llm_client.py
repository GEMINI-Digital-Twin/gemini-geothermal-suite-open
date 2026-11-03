"""One chat client for a local model (Ollama) and an API model (Gemini).

Both speak the OpenAI-compatible ``/chat/completions`` format with tool calls,
so the agent does not care which one answers. Every call is appended to a
JSONL log with the full prompt, the answer, token counts and estimated cost:
that log is the "prompts, answers and tokens" deliverable.

``ScriptedLLM`` replays a fixed list of answers. It lets the loop and tools be
tested offline at zero cost.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

AGENT_DIR = Path(__file__).resolve().parent
HACKATHON_DIR = AGENT_DIR.parent


def load_env(path=HACKATHON_DIR / ".env"):
    """Read KEY=VALUE lines from hackathon/.env into os.environ (no extra package)."""
    if not Path(path).exists():
        return
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_llm_config(path=AGENT_DIR / "llm_config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TokenLog:
    """Append-only JSONL log of every LLM call, with running totals."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.totals = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0,
                       "by_model": {}}

    def write(self, record):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        t = self.totals
        t["calls"] += 1
        t["prompt_tokens"] += record["usage"]["prompt_tokens"]
        t["completion_tokens"] += record["usage"]["completion_tokens"]
        t["cost_usd"] += record["cost_usd"]
        m = t["by_model"].setdefault(record["model"], {"calls": 0, "prompt_tokens": 0,
                                                       "completion_tokens": 0, "cost_usd": 0.0})
        m["calls"] += 1
        m["prompt_tokens"] += record["usage"]["prompt_tokens"]
        m["completion_tokens"] += record["usage"]["completion_tokens"]
        m["cost_usd"] += record["cost_usd"]


class ChatModel:
    """OpenAI-compatible chat endpoint (Ollama or Gemini)."""

    def __init__(self, route_name, route, log, temperature=0.2, timeout=300):
        self.name, self.route, self.log = route_name, route, log
        self.temperature, self.timeout = temperature, timeout

    def chat(self, messages, tools=None, step=None):
        key_env = self.route.get("api_key_env")
        headers = {"Content-Type": "application/json"}
        if key_env:
            key = os.environ.get(key_env)
            if not key:
                raise RuntimeError(f"{key_env} is not set. Add it to hackathon/.env.")
            headers["Authorization"] = f"Bearer {key}"
        body = {"model": self.route["model"], "messages": messages,
                "temperature": self.temperature}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        t0 = time.time()
        r = requests.post(self.route["base_url"].rstrip("/") + "/chat/completions",
                          headers=headers, json=body, timeout=self.timeout)
        if r.status_code >= 400:
            raise RuntimeError(f"{self.name} returned {r.status_code}: {r.text[:500]}")
        data = r.json()
        msg = data["choices"][0]["message"]
        usage = data.get("usage") or {}
        usage = {"prompt_tokens": int(usage.get("prompt_tokens", 0)),
                 "completion_tokens": int(usage.get("completion_tokens", 0))}
        cost = (usage["prompt_tokens"] * self.route.get("price_in_per_mtok_usd", 0)
                + usage["completion_tokens"] * self.route.get("price_out_per_mtok_usd", 0)) / 1e6
        self.log.write({
            "time": datetime.now(timezone.utc).isoformat(), "step": step, "route": self.name,
            "model": self.route["model"], "latency_s": round(time.time() - t0, 2),
            "messages": messages, "response": msg, "usage": usage, "cost_usd": cost,
        })
        return msg


class ScriptedLLM:
    """Replays prepared assistant messages; logs them like a real call (0 tokens)."""

    def __init__(self, script, log, name="scripted"):
        self.script, self.log, self.name = list(script), log, name

    def chat(self, messages, tools=None, step=None):
        if not self.script:
            raise RuntimeError("ScriptedLLM ran out of answers")
        msg = self.script.pop(0)
        if callable(msg):
            msg = msg(messages)
        self.log.write({"time": datetime.now(timezone.utc).isoformat(), "step": step,
                        "route": self.name, "model": self.name, "latency_s": 0,
                        "messages": messages, "response": msg,
                        "usage": {"prompt_tokens": 0, "completion_tokens": 0}, "cost_usd": 0.0})
        return msg


def tool_call(name, args, call_id=None):
    """Build an assistant message that calls one tool (for scripts and tests)."""
    call_id = call_id or f"call_{name}_{abs(hash(json.dumps(args, sort_keys=True))) % 10**6}"
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": call_id, "type": "function",
         "function": {"name": name, "arguments": json.dumps(args)}}]}
