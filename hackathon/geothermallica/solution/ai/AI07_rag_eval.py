"""Eight GEMINI questions through AI06: expected module in the top 5, keyword in the answer, grounding problems; writes runs/rag_eval.md."""
import time

import AI01_log as log
import AI06_rag as rag

# question, sources of which one must be retrieved (module path or note file, as AI06 labels them), keyword the answer must contain
QUESTIONS = [
    ("What does the DPDT class compute?", ("gemini_model/well/pressure_drop.py",), "friction"),
    ("How does the ESP head law read the pump curve at a frequency other than 60 Hz?",
     ("gemini_model/pump/esp.py", "gemini_model/pump/esp_affinity.py"), "60"),
    ("Which input keys does HeatpumpBasic take?", ("gemini_model/heatpump/heatpump_basic.py",), "Ts_in"),
    ("What is the sign of the injector flow rate in the nodal solver?",
     ("gemini_simulator/nodal_solver.py", "gemini_model/well/pressure_drop.py", "PATCH.md"), "down"),
    ("What does HenryGasBubblePoint return?", ("gemini_model/fluid/henry_gas.py",), "bubble"),
    ("What inputs does the AbsorptionChiller need?", ("gemini_model/chiller/absorption_chiller.py",), "floor"),
    ("What does DoubletThermalBreakthrough compute?", ("gemini_model/reservoir/thermal_breakthrough.py",), "interference"),
    ("What is in registry.py?", ("gemini_simulator/registry.py",), "type"),
]


def main():
    rag.index()   # build the corpus and embed new chunks once, before the clock starts
    rows = []
    for q, want, word in QUESTIONS:
        r = rag.answer(q)
        got = [s["source"] for s in r["sources"]]
        hit, kw = any(s in want for s in got), word.lower() in r["answer"].lower()
        rows.append((q, hit, kw, len(r["problems"]), r["tokens"]["prompt"], r["tokens"]["completion"], r["tokens"]["seconds"],
                     ", ".join(s.split("/")[-1] for s in got)))
        print(f"{'hit ' if hit else 'MISS'} {'kw ' if kw else 'NOKW'} {len(r['problems'])} problems  {q}")
    n = len(rows)
    body = "\n".join("| " + " | ".join(str(x) for x in row) + " |" for row in rows)
    tot = (f"retrieval {sum(r[1] for r in rows)}/{n}, keyword {sum(r[2] for r in rows)}/{n}, answers with zero grounding problems "
           f"{sum(r[3] == 0 for r in rows)}/{n}, prompt tokens {sum(r[4] for r in rows)}, completion tokens {sum(r[5] for r in rows)}, "
           f"{sum(r[6] for r in rows):.0f} s, 0 EUR")
    out = (f"# RAG evaluation on GEMINI's source, {log.DEFAULT_MODEL}, embeddings {rag.EMBED_MODEL}, {time.strftime('%Y-%m-%d %H:%M')}\n\n"
           f"k={rag.K}, chunks <= {rag.MAX_CHARS} chars, score {rag.W_COSINE} cosine + {1 - rag.W_COSINE:.1f} keyword, "
           f"refuse below cosine {rag.MIN_COSINE}, at most {rag.PER_SOURCE} chunks per module.\n\n"
           "| question | retrieval hit | keyword hit | grounding problems | prompt tok | completion tok | s | top-5 sources |\n"
           f"|---|---|---|---|---|---|---|---|\n{body}\n\n{tot}\n")
    (log.RUNS / "rag_eval.md").write_text(out)
    print(out)


if __name__ == "__main__":
    main()
