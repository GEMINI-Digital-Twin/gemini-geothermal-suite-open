"""Index every committed agent transcript (one Markdown file per session) with its token use.

Writes simulator_examples/agent_transcripts_index.md. Reads only the transcripts' own "Token use"
tables, so the numbers are exactly what each session logged.

    python simulator_examples/build_transcript_index.py
"""

import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "agent_transcripts_index.md"
BENCH = ROOT / "agent_bench_results" / "2026-11-04-max"
OBJ = ROOT / "agent_compare_results" / "2026-11-04-objective-newdefaults"
CASES = {
    "B0": "off-topic question (weather in Delft)",
    "B1": "cheapest design",
    "B3": "lowest CO2 under a cost cap",
    "B4": "new prices",
    "B5a": "incomplete question: ask if it matters",
    "B5b": "do not ask in vain",
    "B6": "impossible request",
    "B8": "false premise",
    "B9": "push-back",
    "B10": "prompt injection",
    "B13": "review a bugged model",
}


def totals(md):
    """Totals from one transcript's token table, or None if it has none."""
    text = md.read_text(encoding="utf-8")
    m = re.search(r"\| \*\*total\*\* \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|", text)
    gate = sum(
        int(g)
        for g in re.findall(
            r"^\|[^|\n]+\|[^|\n]+\|[^|\n]+\|[^|\n]+\|[^|\n]+\| (\d+) \| \w+ \|$", text, re.M
        )
    )
    outcome = re.findall(
        r"\| (\d+) \| (answer|ask_user|step_limit|error|refused|[a-z_]+) \|$", text, re.M
    )
    if not m:
        return None
    calls, tools, pin, pout = map(int, m.groups())
    out = outcome[-1][1] if outcome else ""
    if calls == 0 and out == "failed":
        out = "no LLM reply (credit or plan limit)"
    return dict(calls=calls, tools=tools, pin=pin, pout=pout, gate=gate, outcome=out)


def model_of(folder):
    """Model name from a run folder (drops _rerun, _partN and _fill_* suffixes)."""
    return re.sub(r"(_rerun|_part\d+|_fill_\w+)$", "", folder)


rows, agg = [], defaultdict(lambda: [0, 0, 0, 0, 0, 0])
for md in sorted(BENCH.glob("*/**/transcripts/*.md")):
    t = totals(md)
    if not t:
        continue
    rel = md.relative_to(BENCH)
    model = model_of(rel.parts[0])
    case = md.stem
    run = next((p for p in rel.parts if re.fullmatch(r"r\d+", p)), "")
    rows.append((model, case, run, t, md.relative_to(ROOT.parent).as_posix()))
    a = agg[model]
    a[0] += 1
    a[1] += t["calls"]
    a[2] += t["tools"]
    a[3] += t["pin"]
    a[4] += t["pout"]
    a[5] += t["calls"] > 0

obj = []
for md in sorted(OBJ.glob("*/transcripts/*.md")) + sorted(OBJ.glob("sol_r1_continued/*.md")):
    if md.name == "index.md":
        continue
    t = totals(md)
    if t:
        run = md.parent.parent.name if md.parent.name == "transcripts" else md.parent.name
        who = "GPT-6.1 Sol" if run.startswith("sol") else "DeepSeek V4.1 Flash"
        obj.append(
            (
                f"{who}, {run}",
                t,
                md.relative_to(ROOT.parent).as_posix(),
            )
        )


def row(*cells):
    """One Markdown table row."""
    return "| " + " | ".join(str(c) for c in cells) + " |"


def header(*cols):
    """Markdown table header and rule."""
    return [row(*cols), "|" + "---|" * len(cols)]


B = "agent_bench_results/2026-11-04-max/<model>/.../"
D = "agent_compare_results/2026-11-04-objective-newdefaults/"
L = [
    "# Agent transcripts and token use, one file per session",
    "",
    "Author: Sa'eed Telvari",
    "",
    "Every agent session is committed as its own Markdown transcript: the user's question, "
    "each LLM call with its prompt and completion tokens, every tool call with its result, "
    "every physics-gate verdict, and a token table at the end. This index lists them with the "
    "totals from those tables. Rebuild: `python simulator_examples/build_transcript_index.py`.",
    "",
    "## Sessions that show the asked-for behaviour",
    "",
    *header("behaviour", "case", "where"),
    row("Irrelevant question: declines without tools", "B0", f"`{B}B0/r*/transcripts/B0.md`"),
    row(
        "Incomplete question: asks for the missing input only when it changes the answer",
        "B5a",
        f"`{B}B5a/r*/transcripts/B5a.md`",
    ),
    row(
        "Incomplete question: does not ask when it does not matter",
        "B5b",
        f"`{B}B5b/r*/transcripts/B5b.md`",
    ),
    row(
        "Impossible request, false premise, push-back, prompt injection",
        "B6, B8, B9, B10",
        f"`{B}B6`, `B8`, `B9`, `B10`",
    ),
    row("Writes or reviews a missing model", "B13", f"`{B}B13/r*/transcripts/B13.md`"),
    row("Full design brief, live, max reasoning (DeepSeek r1–r3, Sol)", "scenario 10", f"`{D}`"),
    row(
        "Agent asks the user (grid capacity) and continues after the answer",
        "scenario 10, Sol",
        f"`{D}sol_r1/`, then `{D}sol_r1_continued/` (PR #42)",
    ),
    "",
    "## Token use per model, 4 Nov benchmark (all committed sessions)",
    "",
    "Includes sessions that a credit or plan limit cut short (no LLM reply); the scored set is "
    "in `agent_bench_results/2026-11-04-max/merged/`.",
    "",
    *header(
        "model",
        "sessions",
        "sessions with an LLM reply",
        "LLM calls",
        "tool calls",
        "prompt tokens",
        "completion tokens",
        "prompt tokens per session with a reply",
    ),
]
for model, (n, c, tl, pi, po, live) in sorted(agg.items()):
    L.append(
        row(model, n, live, f"{c:,}", f"{tl:,}", f"{pi:,}", f"{po:,}", f"{pi // max(live, 1):,}")
    )
L += ["", "## Full design brief sessions (4 Nov, max reasoning)", ""]
L += header(
    "session",
    "LLM calls",
    "tool calls",
    "prompt tokens",
    "completion tokens",
    "gate rejections",
    "outcome",
    "transcript",
)
for name, t, path in obj:
    L.append(
        row(
            name,
            t["calls"],
            t["tools"],
            f"{t['pin']:,}",
            f"{t['pout']:,}",
            t["gate"],
            t["outcome"],
            f"`{path}`",
        )
    )
L += ["", "## Every benchmark session", ""]
L += header(
    "model",
    "case",
    "run",
    "LLM calls",
    "tool calls",
    "prompt tokens",
    "completion tokens",
    "gate rejections",
    "outcome",
    "transcript",
)
for model, case, run, t, path in rows:
    L.append(
        row(
            model,
            f"{case} ({CASES.get(case, '')})",
            run,
            t["calls"],
            t["tools"],
            f"{t['pin']:,}",
            f"{t['pout']:,}",
            t["gate"],
            t["outcome"],
            f"`{path}`",
        )
    )
OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print(len(rows), "benchmark sessions,", len(obj), "design sessions ->", OUT)
