"""Resume a live agent session that ended with an ask_user question, by giving it the answer.

The agent keeps a question open (``pending_question``) and continues the same episode when
the user replies. A scripted run (run_agent_transcripts.py) ends after the question, so its
in-memory episode is lost. This script rebuilds that episode from the session's JSONL
transcript and then sends the user's answer, so the model continues where it stopped:

1. The original question is sent as the first user message, as before.
2. Every logged LLM step is replayed as the same assistant message (the same tool calls with
   the same arguments; the hidden reasoning is not part of the history in either case).
3. Every tool call is re-executed against the ORIGINAL workspace. Runs are deterministic, and
   the run ledger returns the identical earlier run, so the tool results are the ones the model
   saw. Each replayed result is checked against the logged preview. The wall-clock ``seconds``
   are set to the logged values, and a ``reused_earlier_run`` flag is dropped where the
   original result did not have it. Any other mismatch stops the script.
4. The answer to the open question is then sent through ``DesignAgent.ask`` exactly as a user
   reply. From there on everything is live (new LLM calls, tools and physics gate).

The continuation is written as a new transcript (``<session>_continued``) in the same
workspace. Nothing is injected beyond the logged history and the user's answer.

    $env:PYTHONPATH="src"; $env:GEMINI_AGENT_REASONING_EFFORT="max"
    python simulator_examples/resume_agent_session.py --provider codex --model gpt-6.1-sol \
        --workspace simulator_examples/outputs/agent_objective_nd_sol_r1 \
        --session 10_design_with_objective \
        --knmi simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt \
        --answer "I don't know. The brief gives no grid connection capacity or cost."
"""

import argparse
import json
import sys
from pathlib import Path

from gemini_agent.agent import PREVIEW_CHARS, DesignAgent
from gemini_agent.config import AgentConfig
from gemini_agent.tools import compact_json

sys.path.insert(0, str(Path(__file__).parent))
from run_agent_transcripts import _with_weather  # noqa: E402


def load_events(path):
    """The transcript's JSONL events, in order."""
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def rebuild(agent, events):
    """Replay the logged episode into ``agent``; return the open question's text."""
    users = [e for e in events if e["kind"] == "user"]
    replies = [e for e in events if e["kind"] == "reply"]
    if len(users) != 1 or not replies or replies[-1].get("reply_kind") != "question":
        raise SystemExit("expected one user turn that ended with an ask_user question")
    question = users[0]["text"]
    agent.scratch.clear()
    agent.scratch.question = question
    agent.episode = [{"role": "user", "content": question}]
    tools = iter(e for e in events if e["kind"] == "tool")
    n_call = 0
    for ev in events:
        if ev["kind"] != "llm":
            continue
        agent.scratch.steps += 1
        calls = []
        for call in ev.get("tool_calls") or []:
            n_call += 1
            calls.append({"id": f"call_{n_call}", **call})
        msg = {"role": "assistant", "content": ev.get("content") or ""}
        if calls:
            msg["tool_calls"] = [
                {
                    "id": c["id"],
                    "type": "function",
                    "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])},
                }
                for c in calls
            ]
        agent.episode.append(msg)
        for c in calls:
            logged = next(tools)
            if logged["name"] != c["name"] or logged["arguments"] != c["arguments"]:
                raise SystemExit(f"transcript out of order at {c['name']}")
            if c["name"] == "ask_user":
                result = {"status": "question sent to the user; wait for the answer"}
            else:
                result = agent.tools.call(c["name"], c["arguments"])
                if isinstance(result, dict):
                    if "seconds" in result:
                        result["seconds"] = logged.get("seconds", result["seconds"])
                    if (
                        result.get("reused_earlier_run")
                        and "reused_earlier_run" not in logged["result_preview"]
                    ):
                        result.pop("reused_earlier_run")
            content = compact_json(result)
            if content[:PREVIEW_CHARS] != logged["result_preview"]:
                print(f"--- replay mismatch in {c['name']} ({c['id']})")
                print("logged:  ", logged["result_preview"][:300])
                print("replayed:", content[:300])
                raise SystemExit("replayed tool result differs from the logged one; stopping")
            agent.scratch.tool_results.append((c["name"], result))
            agent.episode.append(
                {"role": "tool", "tool_call_id": c["id"], "name": c["name"], "content": content}
            )
    agent.pending_question = True
    print(f"replayed {agent.scratch.steps} LLM steps and {n_call} tool calls, all matching")
    return replies[-1]["text"]


def main():
    """Rebuild the session, send the answer, write the continued transcript."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--workspace", required=True, help="the original run's agent workspace")
    p.add_argument("--session", required=True, help="transcript name (scenario key)")
    p.add_argument("--answer", required=True, help="the user's reply to the open question")
    p.add_argument("--knmi", help="KNMI file, if the original run used measured weather")
    p.add_argument("--year", type=int, default=2025)
    p.add_argument("--provider")
    p.add_argument("--model")
    p.add_argument("--dry-run", action="store_true", help="replay and check only; no LLM call")
    args = p.parse_args()

    ws = Path(args.workspace)
    events = load_events(ws / "transcripts" / f"{args.session}.jsonl")
    overrides = {k: v for k, v in {"provider": args.provider, "model": args.model}.items() if v}
    config = AgentConfig.load(None, workspace=str(ws), **overrides)
    meta = {
        "backend_note": "live LLM; continued session",
        "resumed_from": f"{args.session}.jsonl (episode replayed, tool results re-checked)",
    }
    if args.knmi:
        meta["weather"] = f"KNMI {Path(args.knmi).name} ({args.year})"
    llm = None
    if args.dry_run:
        from gemini_agent.llm import ScriptedLLM

        llm = ScriptedLLM([])
    agent = DesignAgent(config, llm=llm, session_name=f"{args.session}_continued", meta=meta)
    if args.knmi:
        agent.demand = agent.tools.demand = _with_weather(agent.demand, args.knmi, args.year)
    open_question = rebuild(agent, events)
    print(f"agent asked> {open_question}")
    if args.dry_run:
        return
    print(f"user> {args.answer}")
    reply = agent.ask(args.answer)
    print(f"agent ({reply.kind})> {reply.text}")
    agent.close()


if __name__ == "__main__":
    main()
