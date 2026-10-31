"""LLM backends: local Ollama (qwen3:8b by default) and a scripted fake for tests."""

import re

THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def _get(o, k, default=None):
    return o.get(k, default) if isinstance(o, dict) else getattr(o, k, default)


class OllamaLLM:
    """Open-weight model served locally by Ollama. Thinking off by default:
    in our tool-calling test qwen3:8b passed 7/7 tasks at 1.6 s/task without
    thinking vs 12.1 s with it."""

    def __init__(self, model="qwen3:8b", think=False, num_ctx=8192, temperature=0.0):
        import ollama  # imported here so tests run without Ollama installed
        self._ollama = ollama
        self.model, self.think, self.num_ctx, self.temperature = model, think, num_ctx, temperature

    def chat(self, messages, tools):
        kw = dict(model=self.model, messages=messages, tools=tools,
                  options={"temperature": self.temperature, "num_ctx": self.num_ctx}, think=self.think)
        try:
            resp = self._ollama.chat(**kw)
        except TypeError:  # older client without `think`
            kw.pop("think")
            resp = self._ollama.chat(**kw)
        msg = _get(resp, "message")
        calls = []
        for tc in _get(msg, "tool_calls") or []:
            fn = _get(tc, "function")
            calls.append({"name": _get(fn, "name"), "arguments": dict(_get(fn, "arguments") or {})})
        return {
            "content": THINK_RE.sub("", _get(msg, "content") or "").strip(),
            "tool_calls": calls,
            "prompt_tokens": _get(resp, "prompt_eval_count", 0) or 0,
            "output_tokens": _get(resp, "eval_count", 0) or 0,
        }


class ScriptedLLM:
    """Test double: ``script(messages) -> {"content", "tool_calls"}``."""

    def __init__(self, script, model="scripted"):
        self.script, self.model = script, model

    def chat(self, messages, tools):
        out = self.script(messages)
        return {"content": out.get("content", ""), "tool_calls": out.get("tool_calls", []),
                "prompt_tokens": sum(len(str(m.get("content", ""))) for m in messages) // 4,
                "output_tokens": len(out.get("content", "")) // 4 + 20 * len(out.get("tool_calls", []))}
