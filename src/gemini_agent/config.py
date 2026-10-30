"""Agent configuration: LLM endpoint, model, limits and output folders.

Values come from, in increasing priority: the defaults below, a JSON
file (``agent_config.json`` or ``--config``), and environment variables
``GEMINI_AGENT_<FIELD>`` (e.g. ``GEMINI_AGENT_MODEL``,
``GEMINI_AGENT_BASE_URL``, ``GEMINI_AGENT_API_KEY``).

The API key in the repository is a placeholder. Local Ollama ignores it;
for a hosted endpoint put the real key in ``GEMINI_AGENT_API_KEY``, never
in a committed file.
"""

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

PLACEHOLDER_API_KEY = "YOUR_API_KEY_HERE"

# Ready-made endpoint presets (all OpenAI-compatible chat/completions).
PRESETS = {
    "ollama": {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:7b-instruct"},
    "llamacpp": {"base_url": "http://localhost:8080/v1", "model": "qwen2.5-7b-instruct"},
    "vllm": {"base_url": "http://localhost:8000/v1", "model": "Qwen/Qwen2.5-7B-Instruct"},
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "qwen/qwen-2.5-72b-instruct",
    },
}


@dataclass
class AgentConfig:
    """Settings for one agent session."""

    provider: str = "ollama"
    base_url: str = PRESETS["ollama"]["base_url"]
    model: str = PRESETS["ollama"]["model"]
    api_key: str = PLACEHOLDER_API_KEY
    temperature: float = 0.1
    max_tokens: int = 1200
    request_timeout_s: float = 300.0
    native_tool_calling: bool = True  # False: tools described in the prompt, JSON replies parsed
    max_steps_per_question: int = 14  # LLM calls before the agent gives up on one question
    max_gate_retries: int = 3  # rejected final answers before giving up
    workspace: str = "agent_workspace"  # run ledger, notes, transcripts, generated models
    screen_workers: int = 4

    @classmethod
    def load(cls, path=None, env=None, **overrides):
        """Build a config from defaults, an optional JSON file, env vars and overrides."""
        env = os.environ if env is None else env
        values = {}
        if path is not None and Path(path).exists():
            values.update(json.loads(Path(path).read_text()))
        provider = overrides.get("provider") or env.get("GEMINI_AGENT_PROVIDER")
        if provider is None:
            provider = values.get("provider")
        if provider in PRESETS:
            for key, value in PRESETS[provider].items():
                values.setdefault(key, value)
        for f in fields(cls):
            key = f"GEMINI_AGENT_{f.name.upper()}"
            if key in env:
                values[f.name] = _coerce(env[key], f.type)
        values.update({k: v for k, v in overrides.items() if v is not None})
        known = {f.name for f in fields(cls)}
        unknown = set(values) - known
        if unknown:
            raise ValueError(f"Unknown agent config keys: {sorted(unknown)}")
        return cls(**values)

    def public_dict(self):
        """Return the config with the API key masked (safe to log)."""
        d = asdict(self)
        if d["api_key"] and d["api_key"] != PLACEHOLDER_API_KEY:
            d["api_key"] = d["api_key"][:4] + "..." + d["api_key"][-2:]
        return d


def _coerce(text, type_):
    if type_ in (bool, "bool"):
        return text.strip().lower() in ("1", "true", "yes", "on")
    if type_ in (int, "int"):
        return int(text)
    if type_ in (float, "float"):
        return float(text)
    return text
