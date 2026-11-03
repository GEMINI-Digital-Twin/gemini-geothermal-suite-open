"""Token table (per run type from the run files, per model from the log); run: python AI08_tokens.py."""
import json
import re
from collections import defaultdict

import AI01_log as log

LINE = re.compile(r"(\d+) model calls, (\d+) prompt tokens, (\d+) completion tokens")
SECS = re.compile(r"([\d.]+) s (?:wall|in the model)")   # rag files give wall only, the oldest file model time only
PRICE = ("Claude Haiku 4.5", 1.0, 5.0, "https://platform.claude.com/docs/en/about-claude/pricing (read 2026-11-02)")  # USD/MTok in, out [L]


# {type: [calls, prompt, completion, seconds]} from each run file's Tokens line; type = plan / free / rag / other
def run_rows():
    rows = defaultdict(list)
    for path in sorted(log.RUNS.glob("2*.md")):
        text = path.read_text().split("## Tokens")[-1].split("\n## ")[0]
        m, secs, kind = LINE.search(text), SECS.findall(text), path.stem.split("_")[2]
        if m:
            rows[kind if kind in ("plan", "free", "rag") else "other"].append([float(x) for x in m.groups()] + [float(secs[-1])])
    return rows


def table():
    out = ["# Tokens used [C]", "", "## Per run type (run files)", "",
           "| type | runs | model calls | prompt mean | prompt total | completion mean | completion total | wall s mean |",
           "|---|---|---|---|---|---|---|---|"]
    for kind, rs in sorted(run_rows().items()):
        n, s = len(rs), [sum(col) for col in zip(*rs)]
        out.append(f"| {kind} | {n} | {s[0]:.0f} | {s[1] / n:.0f} | {s[1]:.0f} | {s[2] / n:.0f} | {s[2]:.0f} | {s[3] / n:.1f} |")
    recs = [json.loads(line) for line in log.LOG.read_text().splitlines()] if log.LOG.exists() else []
    by = defaultdict(list)
    for r in recs:
        by[r["model"]].append(r)
    out += ["", "## Per model (runs/ai_log.jsonl, every call)", "", "| model | calls | prompt tokens | completion tokens | s in the model |",
            "|---|---|---|---|---|"]
    for model, rs in sorted(by.items()):
        s = log.summary(rs, show=False)
        out.append(f"| {model} | {s['calls']} | {s['prompt_tokens']} | {s['completion_tokens']} | {s['wall_s']:.0f} |")
    t = log.summary(recs, show=False)
    name, p_in, p_out, url = PRICE
    usd = (t["prompt_tokens"] * p_in + t["completion_tokens"] * p_out) / 1e6
    out += ["", f"**Grand total:** {t['calls']} calls, {t['prompt_tokens']} prompt + {t['completion_tokens']} completion = "
            f"{t['prompt_tokens'] + t['completion_tokens']} tokens, {t['wall_s']:.0f} s in the model [C].", "",
            "**Cost:** 0 EUR, local Ollama on the laptop (electricity not counted) [C].", "",
            f"**Hosted comparison:** the same tokens at {name} list price (${p_in:g} / ${p_out:g} per million input / output "
            f"tokens [L, {url}]) would cost {usd:.2f} USD [C].", ""]
    return "\n".join(out)


if __name__ == "__main__":
    text = table()
    (log.RUNS / "tokens.md").write_text(text)
    print(text + f"\nwrote {log.RUNS / 'tokens.md'}")
