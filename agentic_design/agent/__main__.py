"""Chat with the design agent, or run the scripted demo for the evidence appendix.

    python -m agentic_design.agent                 # interactive chat (qwen3:8b via Ollama)
    python -m agentic_design.agent --demo          # scripted questions -> transcripts/demo_*.md
    python -m agentic_design.agent --model qwen3:14b --think

In chat: /stats shows token use, /save writes the transcript, /exit quits.
"""

import argparse
import time
from pathlib import Path

from agentic_design.agent.core import Agent
from agentic_design.agent.llm import OllamaLLM
from agentic_design.agent.memory import DEFAULT_PATH, Memory
from agentic_design.agent.tools import ToolBox

TRANSCRIPTS = Path(__file__).resolve().parent.parent / "transcripts"

DEMO = [
    ("normal", "What heating and cooling demand do we have to meet, and what limits apply?"),
    ("design", "Find the plant design with the lowest CO2 emissions that respects the constraints. Compare at least two depths."),
    ("incomplete", "What COP will our heat pump have?"),
    ("missing input", "Use the network return temperature the organisers specified and tell me how it changes the best design."),
    ("user-given value", "Our district heating network actually returns at 45 C. Re-evaluate the best design with that."),
    ("irrelevant", "Who won the football match last night?"),
    ("explain", "Why does a third doublet not help at 2500 m? Use the results to explain."),
]


def save(agent, name):
    TRANSCRIPTS.mkdir(exist_ok=True)
    p = TRANSCRIPTS / f"{name}_{time.strftime('%Y%m%d_%H%M%S')}.md"
    p.write_text(agent.transcript_markdown(name.replace("_", " ")), encoding="utf-8")
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--think", action="store_true", help="enable thinking (slower, more tokens)")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--reset-memory", action="store_true", help="start with empty long-term memory")
    ap.add_argument("--keep-turns", type=int, default=1,
                    help="earlier questions kept in the conversation (token saving; -1 keeps all)")
    args = ap.parse_args()

    mem_path = DEFAULT_PATH.with_name("demo_log.json") if args.demo else DEFAULT_PATH
    if args.reset_memory or args.demo:
        mem_path.unlink(missing_ok=True)
    agent = Agent(OllamaLLM(args.model, think=args.think), ToolBox(Memory(mem_path)),
                  keep_turns=None if args.keep_turns < 0 else args.keep_turns)

    if args.demo:
        for kind, q in DEMO:
            print(f"\n=== [{kind}] {q}")
            t = time.time()
            print(agent.ask(q))
            print(f"--- {time.time() - t:.1f} s")
        print("\nStats:", agent.stats)
        print("Transcript:", save(agent, "demo"))
        return

    print(f"Design agent ({args.model}). /stats, /save, /exit")
    while True:
        try:
            q = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q == "/exit":
            break
        if q == "/stats":
            print(agent.stats)
            continue
        if q == "/save":
            print("saved:", save(agent, "chat"))
            continue
        t = time.time()
        print("\nagent>", agent.ask(q), f"\n({time.time() - t:.1f} s)")
    print("saved:", save(agent, "chat"))


if __name__ == "__main__":
    main()
