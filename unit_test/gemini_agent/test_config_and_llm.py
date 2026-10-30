"""Tests for the agent config and the LLM clients (no model server needed)."""

import json

import pytest

from gemini_agent.config import PLACEHOLDER_API_KEY, AgentConfig
from gemini_agent.llm import OpenAICompatibleLLM, ScriptedLLM, parse_text_tool_calls
from gemini_agent.tools import openai_tool_schemas


def test_default_is_local_open_weight_model_with_placeholder_key():
    cfg = AgentConfig.load(env={})
    assert cfg.base_url == "http://localhost:11434/v1"
    assert cfg.model.startswith("qwen")
    assert cfg.api_key == PLACEHOLDER_API_KEY
    # the Ollama preset applies even when no provider is named (Qwen3 needs room to think)
    assert cfg.max_tokens == 4096


def test_env_and_preset_overrides(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({"temperature": 0.3}))
    env = {"GEMINI_AGENT_API_KEY": "sk-secret-123", "GEMINI_AGENT_MAX_GATE_RETRIES": "5"}
    cfg = AgentConfig.load(path, env=env, provider="openrouter")
    assert cfg.base_url.startswith("https://openrouter.ai")
    assert cfg.temperature == 0.3 and cfg.max_gate_retries == 5
    assert "secret" not in json.dumps(cfg.public_dict())


def test_unknown_config_key_is_rejected(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({"modle": "typo"}))
    with pytest.raises(ValueError):
        AgentConfig.load(path, env={})


def test_text_tool_calls_are_parsed():
    names = {"run_design", "screen"}
    call = '{"name": "run_design", "arguments": {"n_doublets": 2}}'
    text = f"Let me run it.\n<tool_call>{call}</tool_call>"
    calls, rest = parse_text_tool_calls(text, names)
    assert calls[0].name == "run_design" and calls[0].arguments == {"n_doublets": 2}
    assert rest == "Let me run it."
    calls, _ = parse_text_tool_calls('{"tool": "screen", "args": {"top": 3}}', names)
    assert calls[0].name == "screen" and calls[0].arguments == {"top": 3}
    calls, _ = parse_text_tool_calls('{"tool": "rm_rf", "args": {}}', names)
    assert calls == []


class _FakeResponse:
    def __init__(self, data, status=200):
        self.data, self.status_code, self.text = data, status, json.dumps(data)

    def json(self):
        return self.data


class _FakeSession:
    def __init__(self, data):
        self.data, self.sent = data, None

    def post(self, url, json, headers, timeout):
        self.sent = {"url": url, "json": json, "headers": headers}
        return _FakeResponse(self.data)


def test_openai_client_native_tool_calls_and_usage():
    data = {
        "model": "qwen2.5:7b-instruct",
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "function": {"name": "describe_inputs", "arguments": "{}"},
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 1234, "completion_tokens": 12},
    }
    session = _FakeSession(data)
    llm = OpenAICompatibleLLM(AgentConfig.load(env={}), session=session)
    resp = llm.chat([{"role": "user", "content": "hi"}], openai_tool_schemas())
    assert session.sent["url"] == "http://localhost:11434/v1/chat/completions"
    assert session.sent["json"]["tools"]
    assert resp.tool_calls[0].name == "describe_inputs"
    assert (resp.prompt_tokens, resp.completion_tokens, resp.estimated_tokens) == (1234, 12, False)


def test_reply_cut_off_at_token_limit_is_flagged():
    data = {"choices": [{"message": {"content": "<think>long..."}, "finish_reason": "length"}]}
    llm = OpenAICompatibleLLM(AgentConfig.load(env={}), session=_FakeSession(data))
    assert llm.chat([{"role": "user", "content": "hi"}], []).truncated


def test_openai_client_text_fallback_estimates_tokens():
    content = '<tool_call>{"name": "list_models", "arguments": {}}</tool_call>'
    session = _FakeSession({"choices": [{"message": {"content": content}}]})
    cfg = AgentConfig.load(env={}, native_tool_calling=False)
    llm = OpenAICompatibleLLM(cfg, session=session)
    msgs = [
        {"role": "user", "content": "q"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "a", "function": {"name": "describe_inputs", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "a", "name": "describe_inputs", "content": "{}"},
    ]
    resp = llm.chat(msgs, openai_tool_schemas())
    assert "tools" not in session.sent["json"]
    assert all(m["role"] in ("user", "assistant") for m in session.sent["json"]["messages"])
    assert resp.tool_calls[0].name == "list_models"
    assert resp.estimated_tokens and resp.prompt_tokens > 0


def test_scripted_llm_reads_earlier_tool_results():
    llm = ScriptedLLM([{"content": "a"}, lambda m: {"content": m[-1]["content"].upper()}])
    assert llm.chat([{"role": "user", "content": "x"}], []).content == "a"
    assert llm.chat([{"role": "tool", "content": "ok"}], []).content == "OK"
    with pytest.raises(RuntimeError):
        llm.chat([], [])


def test_thinking_is_split_from_the_answer():
    from gemini_agent.llm import split_thinking

    thought, text = split_thinking("<think>check units</think>It costs 33.5 EUR/MWh.")
    assert thought == "check units" and text == "It costs 33.5 EUR/MWh."


class _RejectingSession(_FakeSession):
    def post(self, url, json, headers, timeout):
        if "max_tokens" in json:
            return _FakeResponse(
                {"error": {"message": "Unsupported parameter: 'max_tokens' is not supported"}},
                400,
            )
        return super().post(url, json, headers, timeout)


def test_reasoning_model_parameters_and_tokens():
    data = {
        "choices": [{"message": {"content": "<think>x</think>done"}}],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 30,
            "completion_tokens_details": {"reasoning_tokens": 20},
        },
    }
    cfg = AgentConfig.load(env={}, provider="openai")
    assert cfg.reasoning_model and cfg.base_url == "https://api.openai.com/v1"
    session = _FakeSession(data)
    resp = OpenAICompatibleLLM(cfg, session=session).chat([{"role": "user", "content": "q"}], [])
    assert "temperature" not in session.sent["json"]
    assert session.sent["json"]["max_completion_tokens"] == cfg.max_tokens
    assert (resp.content, resp.reasoning, resp.reasoning_tokens) == ("done", "x", 20)
    # an endpoint that rejects max_tokens is retried once with reasoning-model parameters
    plain = AgentConfig.load(env={})
    session = _RejectingSession(data)
    resp = OpenAICompatibleLLM(plain, session=session).chat([{"role": "user", "content": "q"}], [])
    assert resp.content == "done" and plain.reasoning_model


def test_codex_cli_backend_round_trip(tmp_path):
    from gemini_agent.llm import CodexCLILLM, make_llm

    seen = {}

    def runner(cmd, prompt, timeout):
        seen["cmd"], seen["prompt"] = cmd, prompt
        out = cmd[cmd.index("--output-last-message") + 1]
        with open(out, "w", encoding="utf-8") as f:
            f.write('<tool_call>{"name": "describe_inputs", "arguments": {}}</tool_call>')
        usage = {"input_tokens": 900, "output_tokens": 40, "reasoning_output_tokens": 25}
        return 0, json.dumps({"type": "turn.completed", "usage": usage}) + "\n", ""

    cfg = AgentConfig.load(env={}, provider="codex")
    assert isinstance(make_llm(cfg), CodexCLILLM)
    llm = CodexCLILLM(cfg, runner=runner)
    resp = llm.chat([{"role": "user", "content": "design it"}], openai_tool_schemas())
    assert "--sandbox" in seen["cmd"] and "read-only" in seen["cmd"]
    assert "- run_design(" in seen["prompt"] and "design it" in seen["prompt"]
    assert resp.tool_calls[0].name == "describe_inputs"
    assert (resp.prompt_tokens, resp.completion_tokens, resp.reasoning_tokens) == (900, 40, 25)
    assert not resp.estimated_tokens
