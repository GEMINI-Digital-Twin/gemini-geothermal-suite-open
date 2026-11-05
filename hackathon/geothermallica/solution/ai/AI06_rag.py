"""Answer questions about GEMINI's modules from their docstrings (plus GEMINI_MODELS.md), citing module and class:
embedding cosine + rare-word overlap, one local-model answer, grounding check, one re-prompt.
Run: python ai/AI06_rag.py "<question>"   (--build rebuilds the corpus and the embeddings)"""
import ast
import hashlib
import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

import ollama

import AI01_log as log
import AI04_check as checker

SOL, PROMPTS = Path(__file__).parents[1], Path(__file__).parent / "prompts"
DOCS, INDEX = log.RUNS / "gemini_docs.md", log.RUNS / "rag_index.json"
EMBED_MODEL = "snowflake-arctic-embed:latest"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "   # arctic-embed's query instruction
MAX_CHARS, K, MIN_COSINE, W_COSINE, PER_SOURCE = 1500, 5, 0.35, 0.7, 2
STOP = set("what when where which does that this with from have about into than they their there would could gemini".split())
CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")   # [1], [1, 3], [1,3]
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.]*\w)")   # a whole number: not inside m3/h, CO2 or a file name
NONE = "Not in the GEMINI source."


def build_docs():
    """The docstring corpus: AI09 when it is in this checkout, else a short walk over module and class docstrings."""
    try:
        import AI09_gemini_docs
        return AI09_gemini_docs.main(DOCS)   # the fuller corpus (function docstrings, input and output keys)
    except ImportError:
        sys.path.insert(0, str(SOL))
    from geo.gemini_path import DEV_SRC
    src, lines = Path(DEV_SRC), ["# GEMINI documentation", ""]
    for p in sorted(q for pkg in ("gemini_model", "gemini_simulator") for q in (src / pkg).rglob("[!_]*.py")):
        tree = ast.parse(code := p.read_text(errors="ignore"))
        lines += [f"## {p.relative_to(src).as_posix()}", "", ast.get_docstring(tree) or "", ""]
        for c in (n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))):
            keys = sorted(set(re.findall(r"self\.parameters\[\s*[\"'](\w+)", ast.get_source_segment(code, c) or "")))
            lines += [f"### {'class' if isinstance(c, ast.ClassDef) else 'def'} {c.name}", "", ast.get_docstring(c) or "",
                      f"parameters (keys read from the code): {', '.join(keys)}" if keys else "", ""]
    DOCS.write_text("\n".join(lines) + "\n")


def chunks(path):
    """Sections at ## and ### headings, split at blank lines past MAX_CHARS; source = module path (## of the corpus) or file name."""
    sections, h2, h3 = [[None, None, []]], None, None
    for line in path.read_text(errors="ignore").splitlines():
        m = re.match(r"(#{2,3})\s+(.*)", line)
        if m:
            h2, h3 = (m.group(2).strip(), None) if m.group(1) == "##" else (h2, m.group(2).strip())
            sections.append([h2, h3, []])
        sections[-1][2].append(line)
    out = []
    for h2, h3, lines in sections:
        src, head = (h2 or path.name, h3 or "") if path == DOCS else (path.name, h3 or h2 or "")
        cur = []
        for p in [u.strip() for u in re.split(r"\n\s*\n", "\n".join(lines)) if u.strip()] + [None]:
            if cur and (p is None or len("\n\n".join(cur + [p])) > MAX_CHARS) and not re.fullmatch(r"#{2,3}\s+.*", "\n\n".join(cur)):
                out.append({"source": src, "heading": head, "text": "\n\n".join(cur), "embed_text": f"{src} § {head}\n" + "\n\n".join(cur)})
                cur = []
            cur += [p] if p else []
    return out


def embed(texts):
    return [v for i in range(0, len(texts), 32) for v in ollama.Client().embed(model=EMBED_MODEL, input=texts[i:i + 32]).embeddings]


def index(rebuild=False):
    """All chunks with vectors and the word rarity table; only new chunk texts are embedded (cache keyed by sha1)."""
    log.RUNS.mkdir(exist_ok=True)
    if rebuild or not DOCS.exists():
        build_docs()
    notes = [d / n for n in ("GEMINI_MODELS.md",) for d in (SOL, SOL.parent)]   # solution root, or one up on the fork
    cs = [c for f in [DOCS] + notes if f.exists() for c in chunks(f)]
    keys = [hashlib.sha1(c["embed_text"].encode()).hexdigest() for c in cs]
    cache = {} if rebuild or not INDEX.exists() else json.loads(INDEX.read_text())
    new = [(k, c["embed_text"]) for k, c in zip(keys, cs) if k not in cache]
    if new or len(cache) != len(set(keys)):
        cache.update(zip([k for k, _ in new], embed([t for _, t in new]) if new else []))
        cache = {k: cache[k] for k in keys}
        INDEX.write_text(json.dumps(cache))
        print(f"index: {len(cs)} chunks, {len(new)} embedded now")
    cs = [{**c, "vec": cache[k]} for k, c in zip(keys, cs)]
    df = Counter(w for c in cs for w in words(c["embed_text"]))
    return cs, {w: math.log(len(cs) / n) for w, n in df.items()}


def words(text):
    return {w.lower() for w in re.findall(r"\w+(?:\.\d+)?", text)
            if (len(w) >= 4 or w[0].isdigit() or (w.isupper() and len(w) >= 2)) and w.lower() not in STOP}


def retrieve(question, cs, idf):
    """Top K by cosine + rarity-weighted word overlap, at most PER_SOURCE chunks per module."""
    q = embed([QUERY_PREFIX + question])[0]
    qw = {x: idf.get(x, math.log(max(len(cs), 2))) for x in words(question)}
    for c in cs:
        c["cosine"] = sum(x * y for x, y in zip(q, c["vec"])) / (math.hypot(*q) * math.hypot(*c["vec"]) or 1)
        kw = sum(v for x, v in qw.items() if x in c["embed_text"].lower()) / (sum(qw.values()) or 1)
        c["score"] = W_COSINE * c["cosine"] + (1 - W_COSINE) * kw
    out = []
    for c in sorted(cs, key=lambda c: -c["score"]):
        if sum(o["source"] == c["source"] for o in out) < PER_SOURCE:
            out.append(c)
    return out[:K]


def grounding(text, hits):
    """Problems: uncited sentences, citations out of range, numbers not in the cited sources."""
    problems = []
    for s in (s for s in re.split(r"(?<=[.!?\]])\s+", text.strip()) if s):
        cites = [int(n) for c in CITE.findall(s) for n in c.split(",")]
        ok = [h for n, h in enumerate(hits, 1) if n in cites]
        problems += [f"no citation: {s}"] if not cites and NONE.lower()[:-1] not in s.lower() else []
        problems += [f"citation out of range 1-{len(hits)}: {s}"] if len(ok) < len(set(cites)) else []
        problems += [f"number {x} not in the cited sources {cites}: {s}" for x in NUMBER.findall(checker.TAG.sub("", CITE.sub("", s)))
                     if ok and not any(checker.close(x, p) for h in ok for p in NUMBER.findall(h["embed_text"]))]
    return problems


def answer(question, show=False):
    t0, records, problems = time.time(), [], []
    hits = retrieve(question, *index())
    if not hits or max(h["cosine"] for h in hits) < MIN_COSINE:
        text = NONE
    else:
        context = "\n\n".join(f"[{i}] {h['source']} § {h['heading']}\n{h['text']}" for i, h in enumerate(hits, 1))
        msgs = [{"role": "user", "content": (PROMPTS / "rag_answer.md").read_text().replace("{context}", context).replace("{question}", question)}]
        for _ in range(2):   # the answer, then one re-prompt with the problems
            records.append(log.chat(msgs, temperature=0))
            text = records[-1][0]["content"].strip()
            problems = grounding(text, hits)
            if not problems:
                break
            msgs += [{"role": "assistant", "content": text},
                     {"role": "user", "content": (PROMPTS / "rag_recheck.md").read_text().replace("{problems}", "\n".join(problems))}]
    s = log.summary([r for _, r in records], show=False)
    tokens = {"calls": s["calls"], "prompt": s["prompt_tokens"], "completion": s["completion_tokens"], "seconds": round(time.time() - t0, 1)}
    sources = [{"n": i, "source": h["source"], "heading": h["heading"], "cosine": round(h["cosine"], 3)} for i, h in enumerate(hits, 1)]
    src = "".join(f"\n- [{x['n']}] {x['source']} § {x['heading']} (cosine {x['cosine']:.3f})" for x in sources)
    slug = re.sub(r"[^a-z0-9]+", "_", question.lower())[:40].strip("_")
    (log.RUNS / f"{time.strftime('%Y%m%d_%H%M%S')}_rag_{slug}.md").write_text(
        f"# RAG answer, {log.DEFAULT_MODEL}, embeddings {EMBED_MODEL}\n\n**Question.** {question}\n\n## Answer\n\n{text}\n\n"
        f"Grounding problems: {len(problems)}" + "".join(f"\n- {p}" for p in problems) + f"\n\n## Sources\n{src}\n\n## Tokens\n\n"
        f"{tokens['calls']} model calls, {tokens['prompt']} prompt tokens, {tokens['completion']} completion tokens, {tokens['seconds']} s wall\n")
    if show:
        print(f"{text}\n\nsources:{src}\ngrounding problems: {len(problems)}" + "".join(f"\n  {p}" for p in problems))
    return {"answer": text, "sources": sources, "problems": problems, "tokens": tokens}


if __name__ == "__main__":
    index(rebuild=True) if "--build" in sys.argv else answer(" ".join(sys.argv[1:]) or "What does DPDT compute?", show=True)
