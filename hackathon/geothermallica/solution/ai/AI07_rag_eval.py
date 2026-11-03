"""Eight questions through AI06: expected file in the top 5, keyword in the answer, grounding problems; writes runs/rag_eval.md."""
import time

import AI01_log as log
import AI06_rag as rag

# question, files of which one must be retrieved (paths as AI06 labels them), keyword the answer must contain
QUESTIONS = [
    ("Why a heat pump and not a boiler?", ("NOTES_findings.md", "README.md"), "boiler"),
    ("Why 2 doublets?", ("README.md", "NOTES_findings.md", "../research/04_storage_dispatch_economics.md"), "unmet"),
    ("Why does absorption cooling need brine above 78 C?", ("NOTES_findings.md", "README.md"), "78"),
    ("What is wrong with GEMINI's pump head law?", ("NOTES_findings.md",), "affinity"),
    ("What is the SodM injection pressure limit?", ("../research/03_doublet_reservoir_design.md", "explore/tables/08_checks.md"), "bar"),
    ("What are the challenge deliverables?", ("../CHALLENGE.md", "../data/raw/challenge_20261028/GEMINI_Hackathon_Challenge_Requirements.txt"), "video"),
    ("Why does the agent not choose the tools itself?", ("NOTES_findings.md",), "free"),
    ("What is the geothermal share of heating?", ("README.md",), "91.9"),
]


def main():
    rag.index()   # embed new chunks once, before the clock starts
    rows = []
    for q, want, word in QUESTIONS:
        t0 = time.time()
        r = rag.answer(q)
        files = [s["file"] for s in r["sources"]]
        hit, kw = any(f in want for f in files), word.lower() in r["answer"].lower()
        rows.append((q, hit, kw, len(r["problems"]), len(r["repaired"]), r["tokens"]["prompt"], r["tokens"]["completion"], round(time.time() - t0, 1),
                     ", ".join(f.split("/")[-1] for f in files)))
        print(f"{'hit ' if hit else 'MISS'} {'kw ' if kw else 'NOKW'} {len(r['problems'])} problems {len(r['repaired'])} repaired  {q}")

    head = "| question | retrieval hit | keyword hit | grounding problems | citations repaired by code | prompt tok | completion tok | s | top-5 files |\n|---|---|---|---|---|---|---|---|---|"
    body = "\n".join("| " + " | ".join(str(x) for x in row) + " |" for row in rows)
    n = len(rows)
    tot = (f"retrieval {sum(r[1] for r in rows)}/{n}, keyword {sum(r[2] for r in rows)}/{n}, "
           f"answers with zero grounding problems {sum(r[3] == 0 for r in rows)}/{n}, citations repaired by code {sum(r[4] for r in rows)}, "
           f"prompt tokens {sum(r[5] for r in rows)}, completion tokens {sum(r[6] for r in rows)}, {sum(r[7] for r in rows):.0f} s, 0 EUR")
    out = (f"# RAG evaluation, {log.DEFAULT_MODEL}, embeddings {rag.EMBED_MODEL}, {time.strftime('%Y-%m-%d %H:%M')}\n\n"
           f"k={rag.K}, chunks <= {rag.MAX_CHARS} chars (tables whole), score {rag.W_COSINE} cosine + {1 - rag.W_COSINE:.1f} keyword, "
           f"refuse below cosine {rag.MIN_COSINE}, at most {rag.PER_FILE} chunks per file, keywords weighted by rarity.\n\n{head}\n{body}\n\n{tot}\n")
    (log.RUNS / "rag_eval.md").write_text(out)
    print(out)


if __name__ == "__main__":
    main()
