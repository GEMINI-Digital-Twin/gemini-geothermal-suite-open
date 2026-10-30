"""LLM backends behind one small interface.

``OpenAICompatibleLLM`` talks to any ``/v1/chat/completions`` endpoint
(Ollama, llama.cpp server, vLLM, OpenRouter, ...). ``ScriptedLLM``
replays a fixed policy so the agent plumbing, physics gate and logging
can be tested offline and deterministically.

Every backend returns an :class:`LLMResponse` with the assistant text,
zero or more tool calls and token usage (taken from the endpoint, or
estimated at ~4 characters per token when the endpoint does not report
it, flagged ``estimated``).
"""

import json
import re
import time
import uuid
from dataclasses import dataclass, field

import requests


def estimate_tokens(text):
    """Rough token count (about 4 characters per token for English + JSON)."""
    return max(1, len(text) // 4) if text else 0


def messages_tokens(messages):
    """Estimated prompt tokens of a message list."""
    return sum(estimate_tokens(json.dumps(m, default=str)) for m in messages)


@dataclass
class ToolCall:
    """One tool call requested by the model."""

    name: str
    arguments: dict
    id: str = field(default_factory=lambda: "call_" + uuid.uuid4().hex[:8])


@dataclass
class LLMResponse:
    """Normalised assistant turn."""

    content: str
    tool_calls: list
    prompt_tokens: int
    completion_tokens: int
    estimated_tokens: bool = False
    latency_s: float = 0.0
    model: str = ""
    reasoning: str = ""  # hidden reasoning ("thinking") text, logged but not sent back
    truncated: bool = False  # the reply hit the completion token limit
    reasoning_tokens: int = 0  # part of completion_tokens, when the endpoint reports it

    def as_message(self):
        """Return the OpenAI-format assistant message for the conversation history."""
        msg = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                }
                for c in self.tool_calls
            ]
        return msg


_THINK = re.compile(r"<think>(.*?)</think>", re.S)


def split_thinking(content):
    """Split ``<think>...</think>`` blocks (Qwen3, DeepSeek-R1) off the visible text."""
    thoughts = [t.strip() for t in _THINK.findall(content or "")]
    return "\n".join(t for t in thoughts if t), _THINK.sub("", content or "").strip()


_TOOL_TAG = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)


def parse_text_tool_calls(content, tool_names):
    """Extract tool calls written as JSON in plain text.

    Accepts ``<tool_call>{"name": ..., "arguments": {...}}</tool_call>``
    (Qwen/Hermes style) and a bare JSON object with ``name``/``tool`` and
    ``arguments``. Returns ``(calls, remaining_text)``.
    """
    calls, text = [], content or ""
    candidates = _TOOL_TAG.findall(text)
    if candidates:
        text = _TOOL_TAG.sub("", text).strip()
    else:
        obj = _first_json_object(text)
        if obj is not None:
            candidates = [obj]
    for raw in candidates:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        name = data.get("name") or data.get("tool")
        if name in tool_names:
            args = data.get("arguments") or data.get("args") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"_unparsed": args}
            calls.append(ToolCall(name=name, arguments=args))
            if raw in text:
                text = text.replace(raw, "").strip()
    return calls, text


def _first_json_object(text):
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        start = text.find("{", start + 1)
    return None


def _to_plain_messages(messages):
    """Flatten tool-call messages for models without native tool calling."""
    out = []
    for m in messages:
        if m["role"] == "tool":
            out.append(
                {"role": "user", "content": f"[tool result {m.get('name', '')}]\n{m['content']}"}
            )
        elif m["role"] == "assistant" and m.get("tool_calls"):
            calls = "\n".join(
                "<tool_call>"
                + json.dumps(
                    {
                        "name": c["function"]["name"],
                        "arguments": json.loads(c["function"]["arguments"]),
                    }
                )
                + "</tool_call>"
                for c in m["tool_calls"]
            )
            out.append({"role": "assistant", "content": (m.get("content") or "") + "\n" + calls})
        else:
            out.append({"role": m["role"], "content": m.get("content") or ""})
    return out


def _unsupported(text):
    text = text.lower()
    return ("temperature" in text or "max_tokens" in text) and (
        "unsupported" in text or "not supported" in text
    )


class OpenAICompatibleLLM:
    """Chat-completions client for any OpenAI-compatible server."""

    def __init__(self, config, session=None):
        """Store the config; ``session`` can be injected for tests."""
        self.config = config
        self.session = session or requests.Session()

    def chat(self, messages, tools):
        """Send the conversation and tool schemas; return an :class:`LLMResponse`."""
        cfg = self.config
        native = cfg.native_tool_calling
        payload = {
            "model": cfg.model,
            "messages": messages if native else _to_plain_messages(messages),
        }
        if cfg.reasoning_model:
            payload["max_completion_tokens"] = cfg.max_tokens
        else:
            payload["temperature"] = cfg.temperature
            payload["max_tokens"] = cfg.max_tokens
        if native and tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = {"Content-Type": "application/json"}
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"
        url = cfg.base_url.rstrip("/") + "/chat/completions"
        t0 = time.time()
        resp = self.session.post(url, json=payload, headers=headers, timeout=cfg.request_timeout_s)
        if resp.status_code == 400 and "max_tokens" in payload and _unsupported(resp.text):
            # reasoning models reject temperature / max_tokens: retry once, remember it
            cfg.reasoning_model = True
            payload.pop("temperature", None)
            payload["max_completion_tokens"] = payload.pop("max_tokens")
            resp = self.session.post(
                url, json=payload, headers=headers, timeout=cfg.request_timeout_s
            )
        latency = time.time() - t0
        if resp.status_code != 200:
            raise RuntimeError(f"LLM endpoint returned {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        choice = data["choices"][0]
        msg = choice["message"]
        reasoning, content = split_thinking(msg.get("content") or "")
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or reasoning
        tool_names = {t["function"]["name"] for t in tools or []}
        calls = []
        for c in msg.get("tool_calls") or []:
            args = c["function"].get("arguments") or "{}"
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"_unparsed": args}
            calls.append(ToolCall(name=c["function"]["name"], arguments=args, id=c.get("id") or ""))
        if not calls:
            calls, content = parse_text_tool_calls(content, tool_names)
        for c in calls:
            if not c.id:
                c.id = "call_" + uuid.uuid4().hex[:8]
        usage = data.get("usage") or {}
        estimated = "prompt_tokens" not in usage
        return LLMResponse(
            content=content.strip(),
            tool_calls=calls,
            prompt_tokens=usage.get("prompt_tokens", messages_tokens(payload["messages"])),
            completion_tokens=usage.get("completion_tokens", estimate_tokens(content)),
            estimated_tokens=estimated,
            latency_s=latency,
            model=data.get("model", cfg.model),
            reasoning=reasoning if isinstance(reasoning, str) else json.dumps(reasoning),
            reasoning_tokens=(usage.get("completion_tokens_details") or {}).get(
                "reasoning_tokens", 0
            ),
            truncated=choice.get("finish_reason") == "length",
        )


class ScriptedLLM:
    """Deterministic stand-in LLM that follows a scripted policy.

    ``steps`` is a list; each item is either a dict
    ``{"content": str, "tool_calls": [(name, args), ...]}`` or a callable
    ``f(messages) -> dict`` that can read earlier tool results (so its
    final answer quotes real run numbers). Token counts are estimated.
    Used for tests and for the offline demo transcripts, which are
    labelled as scripted.
    """

    def __init__(self, steps, model="scripted-policy"):
        """Store the policy steps."""
        self.steps = list(steps)
        self.model = model
        self.calls = 0

    def chat(self, messages, tools):
        """Return the next scripted turn."""
        if not self.steps:
            raise RuntimeError("ScriptedLLM ran out of steps")
        step = self.steps.pop(0)
        if callable(step):
            step = step(messages)
        self.calls += 1
        content = step.get("content", "")
        calls = [ToolCall(name=n, arguments=a) for n, a in step.get("tool_calls", [])]
        completion = estimate_tokens(content) + sum(
            estimate_tokens(json.dumps(c.arguments)) + 5 for c in calls
        )
        return LLMResponse(
            content=content,
            tool_calls=calls,
            prompt_tokens=messages_tokens(messages) + messages_tokens(tools or []),
            completion_tokens=completion,
            estimated_tokens=True,
            model=self.model,
        )


CODEX_PROTOCOL = """You are the language model inside the GEMINI design agent. Do NOT run shell
commands, read files or edit anything yourself: the only way to act is to request one of
the tools below, which the agent runs for you. Reply in exactly one of two ways:
1. One or more tool requests, each on its own line, exactly like
   <tool_call>{"name": "run_design", "arguments": {"n_doublets": 2}}</tool_call>
2. Your final answer to the user as plain text (no tool_call tags).

Tools:
{tools}

Conversation so far (system instructions first, then user, assistant and tool results):
{conversation}

Your reply:"""


def _tool_list(tools):
    lines = []
    for t in tools or []:
        f = t["function"]
        props = f.get("parameters", {}).get("properties", {})
        args = ", ".join(f"{k}: {v.get('type', 'any')}" for k, v in props.items())
        lines.append(f"- {f['name']}({args}): {f['description']}")
    return "\n".join(lines)


def _find_usage(obj):
    """Return the last ``usage``-like dict (input/output tokens) found in a JSON event."""
    found = None
    if isinstance(obj, dict):
        if "input_tokens" in obj or "output_tokens" in obj:
            found = obj
        for v in obj.values():
            found = _find_usage(v) or found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_usage(v) or found
    return found


class CodexCLILLM:
    """Use the Codex CLI (``codex exec``, signed in with a ChatGPT plan) as the LLM.

    Each agent step runs one non-interactive, ephemeral, read-only ``codex exec`` in an
    empty folder. The conversation and tool list go in as text; tool requests come back
    as ``<tool_call>`` JSON (the same path as ``native_tool_calling = False``). Token
    counts are read from Codex's ``--json`` events; they include Codex's own system
    prompt, so they are not directly comparable with a bare API call.
    """

    def __init__(self, config, runner=None):
        """``runner(cmd, prompt, timeout) -> (returncode, stdout, stderr)`` can be injected."""
        import shutil
        import tempfile

        self.config = config
        self.model = config.model
        self.executable = shutil.which("codex") or "codex"
        self.workdir = tempfile.mkdtemp(prefix="gemini_codex_")
        self.runner = runner or self._run

    @staticmethod
    def _run(cmd, prompt, timeout):
        import subprocess

        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=timeout, encoding="utf-8"
        )
        return proc.returncode, proc.stdout, proc.stderr

    def chat(self, messages, tools):
        """Run one ``codex exec`` turn and return an :class:`LLMResponse`."""
        import os

        conversation = "\n\n".join(
            f"[{m['role']}]\n{m['content']}" for m in _to_plain_messages(messages)
        )
        prompt = CODEX_PROTOCOL.replace("{tools}", _tool_list(tools)).replace(
            "{conversation}", conversation
        )
        out_file = os.path.join(self.workdir, "last_message.txt")
        if os.path.exists(out_file):
            os.remove(out_file)
        cmd = [
            self.executable,
            "exec",
            "--json",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--cd",
            self.workdir,
            "--output-last-message",
            out_file,
        ]
        if self.model and self.model != "default":
            cmd += ["--model", self.model]
        cmd.append("-")
        t0 = time.time()
        code, stdout, stderr = self.runner(cmd, prompt, self.config.request_timeout_s)
        latency = time.time() - t0
        if code != 0:
            raise RuntimeError(f"codex exec failed ({code}): {(stderr or stdout)[-500:]}")
        content = ""
        if os.path.exists(out_file):
            with open(out_file, encoding="utf-8") as f:
                content = f.read()
        usage, reasoning = None, []
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            usage = _find_usage(event) or usage
            item = event.get("item") if isinstance(event, dict) else None
            if isinstance(item, dict) and item.get("type") == "reasoning" and item.get("text"):
                reasoning.append(item["text"])
            if not content and isinstance(item, dict) and item.get("type") == "agent_message":
                content = item.get("text", "")
        thought, content = split_thinking(content)
        calls, content = parse_text_tool_calls(content, {t["function"]["name"] for t in tools})
        details = (usage or {}).get("output_tokens_details") or {}
        return LLMResponse(
            content=content.strip(),
            tool_calls=calls,
            prompt_tokens=int((usage or {}).get("input_tokens", estimate_tokens(prompt))),
            completion_tokens=int((usage or {}).get("output_tokens", estimate_tokens(content))),
            estimated_tokens=usage is None,
            latency_s=latency,
            model=f"codex-cli:{self.model}",
            reasoning="\n".join(reasoning) or thought,
            reasoning_tokens=int(
                (usage or {}).get("reasoning_output_tokens", details.get("reasoning_tokens", 0))
            ),
        )


def make_llm(config):
    """Return the backend for a config (``provider == "scripted"`` is not built here)."""
    if config.provider == "codex":
        return CodexCLILLM(config)
    return OpenAICompatibleLLM(config)
