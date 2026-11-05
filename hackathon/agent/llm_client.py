"""Chat client for the local model (Ollama) and the API model (Gemini).

Both use the OpenAI-style /chat/completions endpoint with tool calls, so the
same code talks to either. Every call is written to a JSONL log with the
prompt, the answer, token counts and estimated cost. That log is what we hand
in as the prompts/answers/tokens record.

ScriptedLLM plays back fixed answers so the loop can be tested offline.
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
    """Put the KEY=VALUE lines of hackathon/.env into os.environ."""
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
    """Writes each LLM call to the JSONL log and keeps running totals."""

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


def _retry_after_s(response, default):
    """Wait time from the Retry-After header if the server sent one, else the default."""
    try:
        return max(1.0, float(response.headers.get("Retry-After")))
    except (TypeError, ValueError):
        return float(default)


class ChatModel:
    """One route (Ollama or Gemini) behind the OpenAI-style chat endpoint."""

    def __init__(self, route_name, route, log, temperature=0.2, timeout=None, retries=1):
        self.name, self.route, self.log = route_name, route, log
        self.temperature = temperature
        self.timeout = timeout or route.get("timeout_s", 300)  # per-route, from llm_config.yaml
        self.retries = retries
        self.max_429_retries = 3   # our choice; the free-tier limit resets within a minute or so
        self.wait_429_s = 30       # our choice, if the server gives no Retry-After
        self._sleep = time.sleep   # replaceable in tests

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
        url = self.route["base_url"].rstrip("/") + "/chat/completions"
        for n_429 in range(self.max_429_retries + 1):
            for attempt in range(self.retries + 1):
                try:
                    r = requests.post(url, headers=headers, json=body, timeout=self.timeout)
                    break
                except (requests.Timeout, requests.ConnectionError) as exc:
                    if attempt == self.retries:
                        raise RuntimeError(f"{self.name} did not answer after {attempt + 1} attempts "
                                           f"({self.timeout} s timeout each): {exc}") from exc
            # 429 means rate limit (free tier): wait and try again rather than stop the run
            if r.status_code != 429 or n_429 == self.max_429_retries:
                break
            wait = _retry_after_s(r, self.wait_429_s)
            print(f"[{self.name}] 429 rate limit, waiting {wait:.0f} s "
                  f"(retry {n_429 + 1}/{self.max_429_retries})")
            self._sleep(wait)
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
    """Plays back prepared answers and logs them like real calls (0 tokens)."""

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
    """Assistant message calling one tool. Used by the demo script and the tests."""
    call_id = call_id or f"call_{name}_{abs(hash(json.dumps(args, sort_keys=True))) % 10**6}"
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": call_id, "type": "function",
         "function": {"name": name, "arguments": json.dumps(args)}}]}
