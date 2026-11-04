"""Token and quality summary of all saved demo transcripts (evidence for the token-reduction bonus).

    python -m agentic_design.token_report                 # reads agentic_design/evidence/*.md
    python -m agentic_design.token_report path/to/folder

Prints one row per run (tokens, LLM calls, tool calls, rejected calls, corrections, answers the checker passed)
and the tokens per question of the last two runs side by side.
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def parse(path):
    t = path.read_text(encoding="utf-8")
    st = {k: int(v) for k, v in re.findall(r"^- ([a-z ]+): (\d+)", t, re.M)}
    per_q = [int(x) for x in re.findall(r"tokens this turn: (\d+)", t)]
    ver = len(re.findall(r"claims verified: yes", t))
    m = re.search(r"v(\d+)", path.stem)
    return {"run": int(m.group(1)) if m else 0, "file": path.name, "per_question": per_q, "checker_passed": ver,
            "questions": len(per_q), "prompt": st.get("prompt tokens", 0), "output": st.get("output tokens", 0),
            "llm_calls": st.get("llm calls", 0), "tool_calls": st.get("tool calls", 0),
            "rejected": st.get("rejected tool calls", 0), "corrections": st.get("claim corrections", 0)}


def main():
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "evidence"
    runs = sorted((parse(p) for p in folder.glob("demo*.md")), key=lambda r: r["run"])
    if not runs:
        print(f"no demo*.md files in {folder}")
        return
    print(f"{'run':>4} {'tokens':>8} {'prompt':>8} {'output':>7} {'LLM calls':>9} {'tools':>6} {'rejected':>8} "
          f"{'corrections':>11} {'checker passed':>14}")
    for r in runs:
        print(f"{r['run']:>4} {r['prompt'] + r['output']:>8,} {r['prompt']:>8,} {r['output']:>7,} {r['llm_calls']:>9} "
              f"{r['tool_calls']:>6} {r['rejected']:>8} {r['corrections']:>11} {r['checker_passed']:>9}/{r['questions']}")
    if len(runs) >= 2:
        a, b = runs[-2], runs[-1]
        print(f"\ntokens per question, run {a['run']} -> run {b['run']}:")
        for i, (x, y) in enumerate(zip(a["per_question"], b["per_question"]), 1):
            print(f"  Q{i}: {x:>7,} -> {y:>7,}  ({(y - x) / x:+.0%})")
        ta, tb = a["prompt"] + a["output"], b["prompt"] + b["output"]
        print(f"  total: {ta:,} -> {tb:,}  ({(tb - ta) / ta:+.0%})")


if __name__ == "__main__":
    main()
