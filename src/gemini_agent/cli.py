"""Command line for the GEMINI GeoDesign agent.

  python -m gemini_agent.cli run    [--model qwen3:4b-instruct-2507-q4_K_M] [--profile
  deep|lean] "<request>"
  python -m gemini_agent.cli chat   [--model ...] [--profile ...] [--router]
  python -m gemini_agent.cli search [--objective balanced]      # physics only, no LLM
  python -m gemini_agent.cli ui                                  # web cockpit on :7860

(set PYTHONPATH=src). ``run`` is batch mode: missing inputs are filled with
documented defaults and logged as assumptions. All runs write
runs/<session>/{trace,transcript,ledger}.jsonl for the evidence appendix.
"""

from __future__ import annotations

import argparse
import json
import sys

DEFAULT_REQUEST = (
    "Design a geothermal heating and cooling system for the supplied 2027 demand profiles. "
    "Balance cost and CO2. Explain every major decision."
)


def _print_turn(turn: dict):
    print("\n" + "=" * 78)
    print(turn["answer"])
    p = turn["provenance"]
    print("-" * 78)
    print(
        f"verifier: {p['numbers_checked']} numbers checked, unsupported: {p['unsupported'] or 'none'}, "  # noqa: E501
        f"unit mismatches: {p.get('unit_mismatches') or 'none'}"
    )
    if (turn.get("router") or {}).get("label"):
        r = turn["router"]
        print(
            f"router: {r['label']} ({r['confidence']:.2f}){' -> answered by router' if r.get('reply') else ''}"  # noqa: E501
        )
    print(
        f"LLM calls {turn['llm_calls']} | prompt tokens {turn['prompt_tokens']:,} | completion "
        f"tokens "
        f"{turn['completion_tokens']:,} | {turn['seconds']} s | tools: {', '.join(turn['tool_calls'])}"  # noqa: E501
    )


def main(argv=None):
    """Entry point."""
    ap = argparse.ArgumentParser(prog="gemini-design")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "chat"):
        sp = sub.add_parser(name)
        sp.add_argument(
            "--model",
            default=None,
            help="Ollama model (default $GEODESIGN_MODEL or qwen3:4b-instruct-2507-q4_K_M)",
        )
        sp.add_argument("--profile", default="deep", choices=["deep", "lean"])
        sp.add_argument("--harness", default="lean", choices=["lean", "default"])
        sp.add_argument(
            "--router",
            action=argparse.BooleanOptionalAction,
            default=None,
            help="calibrated one-letter router before the agent (default $GEODESIGN_ROUTER, off)",
        )
        if name == "run":
            sp.add_argument("request", nargs="?", default=DEFAULT_REQUEST)
    sp = sub.add_parser("search")
    sp.add_argument("--objective", default="balanced", choices=["min_lcoe", "balanced", "min_co2"])
    sub.add_parser("ui")
    a = ap.parse_args(argv)

    if a.cmd == "ui":
        from gemini_agent.ui.app import main as ui_main

        return ui_main()
    if a.cmd == "search":
        from gemini_agent.optimize import search
        from gemini_agent.service import default_service

        out = search(default_service(), a.objective, progress=lambda m: print(m, file=sys.stderr))
        print(json.dumps(out["best"].summary(), indent=1, default=str))
        return 0

    from gemini_agent.router import from_env
    from gemini_agent.runner import AgentRunner

    runner = AgentRunner(
        model=a.model,
        profile=a.profile,
        harness=a.harness,
        mode="auto" if a.cmd == "run" else "interactive",
        router=from_env(a.model, a.router),
    )
    print(f"session {runner.session_id} -> {runner.run_dir}")
    if a.cmd == "run":
        _print_turn(runner.ask(a.request))
        return 0
    while True:
        try:
            msg = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if msg in {"exit", "quit"}:
            return 0
        if msg:
            _print_turn(runner.ask(msg))


if __name__ == "__main__":
    sys.exit(main())
