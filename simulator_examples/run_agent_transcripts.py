"""Run the demo questions through the design agent and save transcripts + token tables.

Backends:
    scripted  deterministic stand-in policy (no model server needed; output is
              labelled "scripted" and only demonstrates tools, gate, memory, logs)
    live      the configured OpenAI-compatible endpoint (default: local Ollama,
              qwen2.5:7b-instruct). Start Ollama and `ollama pull <model>` first.

Run with:
    $env:PYTHONPATH="src"; python simulator_examples/run_agent_transcripts.py --backend live
    PYTHONPATH=src python simulator_examples/run_agent_transcripts.py --backend scripted

Writes ``simulator_examples/outputs/agent_<backend>/`` with one JSONL + Markdown
transcript per scenario, the run ledger, project notes, generated models, and
``index.md`` (all scenarios with token totals).
"""

import argparse
import shutil
import sys
from pathlib import Path

from gemini_agent.agent import DesignAgent
from gemini_agent.config import AgentConfig
from gemini_agent.llm import ScriptedLLM
from gemini_agent.scenarios import SCENARIOS, scripted_steps

OUTPUTS = Path(__file__).parent / "outputs"


def run(backend, only=None, config_path=None, fresh=True):
    """Run the scenarios; return the index rows."""
    workspace = OUTPUTS / f"agent_{backend}"
    if fresh and workspace.exists():
        shutil.rmtree(workspace)
    config = AgentConfig.load(config_path, workspace=str(workspace))
    rows = []
    for key, scenario in SCENARIOS.items():
        if only and key not in only:
            continue
        if backend == "scripted":
            llm = ScriptedLLM(scripted_steps(key))
            meta = {
                "model": "scripted-policy",
                "provider": "offline",
                "backend_note": "SCRIPTED stand-in, not an LLM: demonstrates tools, physics "
                "gate, memory and logging",
            }
        else:
            llm, meta = None, {"backend_note": "live LLM"}
        agent = DesignAgent(config, llm=llm, session_name=key, meta=meta)
        print(f"\n=== {key}: {scenario['title']}")
        kinds = []
        for turn in scenario["turns"]:
            print(f"user> {turn}")
            reply = agent.ask(turn)
            kinds.append(reply.kind)
            print(f"agent ({reply.kind})> {reply.text}")
        _, md = agent.close()
        totals = agent.transcript.totals()
        rejections = sum(1 for e in agent.transcript.events if e["kind"] == "gate_reject")
        rows.append(
            {
                "scenario": key,
                "title": scenario["title"],
                "outcome": " -> ".join(kinds),
                "gate_rejections": rejections,
                "file": md.name,
                **totals,
            }
        )
    _write_index(workspace, backend, config, rows)
    return rows


def _write_index(workspace, backend, config, rows):
    lines = [
        f"# Agent transcripts ({backend})",
        "",
        (
            f"LLM: `{config.model}` at `{config.base_url}`"
            if backend == "live"
            else "Backend: scripted stand-in policy (no LLM). Numbers in answers still come "
            "from real GEMINI runs and pass the physics gate."
        ),
        "",
        "| scenario | outcome | LLM calls | tool calls | prompt tok | completion tok | "
        "gate rejections |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| [{r['title']}]({r['file']}) | {r['outcome']} | {r['llm_calls']} | "
            f"{r['tool_calls']} | {r['prompt_tokens']} | {r['completion_tokens']} | "
            f"{r['gate_rejections']} |"
        )
    lines.append(
        f"| **total** | | {sum(r['llm_calls'] for r in rows)} | "
        f"{sum(r['tool_calls'] for r in rows)} | {sum(r['prompt_tokens'] for r in rows)} | "
        f"{sum(r['completion_tokens'] for r in rows)} | "
        f"{sum(r['gate_rejections'] for r in rows)} |"
    )
    if backend == "scripted":
        lines += ["", "Token counts are estimated at ~4 characters per token."]
    (workspace / "transcripts" / "index.md").write_text("\n".join(lines) + "\n")


def main(argv=None):
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", choices=("scripted", "live"), default="scripted")
    parser.add_argument("--only", nargs="*", help="scenario keys")
    parser.add_argument("--config", help="agent config JSON")
    parser.add_argument("--keep", action="store_true", help="keep the previous workspace")
    args = parser.parse_args(argv)
    run(args.backend, args.only, args.config, fresh=not args.keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
