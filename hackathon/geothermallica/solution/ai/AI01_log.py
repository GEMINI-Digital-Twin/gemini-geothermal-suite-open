"""Every model call goes through chat(): one JSON line per call in runs/ai_log.jsonl (prompt, answer, tokens, times)."""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import ollama

DEFAULT_MODEL = os.environ.get("AGENT_MODEL", "qwen3:4b-instruct-2507-q4_K_M")   # AGENT_MODEL=... swaps the model
DEFAULT_OPTIONS = {"temperature": 0, "seed": 0, "num_ctx": 24576, "num_predict": 4096}   # 4096: the planned answer can pass 2048
RUNS = Path(__file__).parent / "runs"
LOG = RUNS / "ai_log.jsonl"
TIMES = ("prompt_eval_count", "eval_count", "total_duration", "load_duration", "prompt_eval_duration", "eval_duration")


def strip_think(text):
    text = text or ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).split("</think>")[-1].strip()


def chat(messages, tools=None, model=DEFAULT_MODEL, **options):
    opts = {**DEFAULT_OPTIONS, **options}
    r = ollama.Client().chat(model=model, messages=messages, tools=tools, options=opts)
    calls = [{"name": c.function.name, "arguments": dict(c.function.arguments or {})} for c in r.message.tool_calls or []]
    msg = {"role": "assistant", "content": strip_think(r.message.content), "tool_calls": calls}
    rec = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": model, "options": opts,
           "messages": messages, "tools": [t["function"]["name"] for t in tools or []], "response": msg}
    rec.update({k: getattr(r, k, None) for k in TIMES})
    RUNS.mkdir(exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    return msg, rec


def summary(records=None, show=True):
    if records is None:
        records = [json.loads(line) for line in LOG.read_text().splitlines()] if LOG.exists() else []
    s = {"calls": len(records),
         "prompt_tokens": sum(r["prompt_eval_count"] or 0 for r in records),
         "completion_tokens": sum(r["eval_count"] or 0 for r in records),
         "wall_s": sum(r["total_duration"] or 0 for r in records) / 1e9}
    if show:
        print(f"{s['calls']} calls, {s['prompt_tokens']} prompt tokens, {s['completion_tokens']} completion tokens, "
              f"{s['wall_s']:.1f} s in the model")
    return s


if __name__ == "__main__":
    msg, _ = chat([{"role": "user", "content": "say ok"}])
    print("model said:", msg["content"])
    summary()
