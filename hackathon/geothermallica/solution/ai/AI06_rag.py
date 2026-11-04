"""Answer "why" questions from the project notes: hybrid retrieval, cited answer, citation repair, grounding check, one re-prompt.

Run: python ai/AI06_rag.py "<question>"   (--build re-embeds, --files lists the corpus)
"""
import glob
import hashlib
import json
import math
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import AI01_log as log
import AI04_check as checker

SOL = Path(__file__).parents[1]
PROMPTS = Path(__file__).parent / "prompts"
INDEX = log.RUNS / "rag_index.json"
EMBED_MODEL = "snowflake-arctic-embed:latest"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "   # arctic-embed's query instruction
MAX_CHARS, K, MIN_COSINE, W_COSINE, PER_FILE, POOL = 1500, 5, 0.35, 0.7, 2, 20
# kind of each source, shown to the model; design results get a small score bonus
KIND = {"README.md": "design result", "NOTES_findings.md": "design result", "explore/tables": "design result", "ai/runs/eval": "design result",
        "geo/gemini_contrib": "design result", "../research": "research note, written before the design", "../CHALLENGE.md": "challenge brief",
        "../data/raw": "challenge brief", "ai/runs/gemini_docs.md": "GEMINI docstring (TNO)"}
BONUS = 0.05   # added to the score of a design-result chunk
SOURCES = ["README.md", "NOTES_findings.md", "../CHALLENGE.md", "../research/*.md", "explore/tables/08_checks.md",
           "ai/runs/eval_table.md", "../data/raw/challenge_20261028/GEMINI_Hackathon_Challenge_Requirements.txt",
           "geo/gemini_contrib/README.md", "geo/gemini_contrib/PATCH.md", "ai/runs/eval_models.md", "ai/runs/gemini_docs.md"]
# rag_eval.md is left out: the RAG would cite its own evaluation
STOP = set("what when where which does that this with from have about into than they their there would could should".split())
IDF = {}   # word -> log(chunks / chunks holding it), filled by index()
CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")   # [1], [1, 3], [1,3]
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.]*\w)")   # a whole number: not inside m3/h, CO2 or a file name


def prompt(name):
    return (PROMPTS / f"{name}.md").read_text().rstrip("\n")


def files():
    return [p for pat in SOURCES for p in sorted(glob.glob(str(SOL / pat)))]


def chunks(path):
    """Sections at #, ##, ### headings; a section over MAX_CHARS is split at blank lines, one paragraph overlapping."""
    name = os.path.relpath(path, SOL)
    sections, heads, lines, code = [], [], [], False
    for line in Path(path).read_text(errors="ignore").splitlines():
        code ^= line.startswith("```")
        m = None if code else re.match(r"(#{1,3})\s+(.*)", line)
        if m:
            sections.append((" > ".join(heads), lines))
            heads, lines = heads[:len(m.group(1)) - 1] + [m.group(2).strip()], []
        lines.append(line)
    sections.append((" > ".join(heads), lines))
    out = []
    for head, lines in sections:
        paras = [u.strip() for p in re.split(r"\n\s*\n", "\n".join(lines)) for u in split_list(p) if u.strip()]
        cur = []
        for p in paras:
            if cur and len("\n\n".join(cur + [p])) > MAX_CHARS:
                out.append((head, "\n\n".join(cur)))
                cur = cur[-1:] if len(cur[-1]) + len(p) < MAX_CHARS else []   # overlap: last paragraph starts the next
            cur.append(p)
        if cur and not re.fullmatch(r"#{1,3}\s+.*", "\n\n".join(cur)):   # skip a heading with no body
            out.append((head, "\n\n".join(cur)))
    return [{"file": name, "heading": h, "index": i, "text": t} for i, (h, t) in enumerate(out)]


def split_list(para):
    """A paragraph over MAX_CHARS that is a list is split into its items; tables and prose stay whole."""
    return [para] if len(para) <= MAX_CHARS or para.lstrip().startswith("|") else re.split(r"\n(?=\s*(?:[-*]|\d+\.)\s)", para)


def embed(texts):
    import ollama
    return [v for i in range(0, len(texts), 32) for v in ollama.Client().embed(model=EMBED_MODEL, input=texts[i:i + 32]).embeddings]


def index(rebuild=False):
    """All chunks with their vectors; only chunks whose text is new get embedded (cache keyed by sha1)."""
    cs = [c for f in files() for c in chunks(f)]
    for c in cs:
        c["embed_text"] = f"{c['file']} § {c['heading']}\n{c['text']}"
        c["sha1"] = hashlib.sha1(c["embed_text"].encode()).hexdigest()
    cache = {} if rebuild or not INDEX.exists() else json.loads(INDEX.read_text())
    new = [c for c in cs if c["sha1"] not in cache]
    if new or len(cache) != len({c["sha1"] for c in cs}):
        cache.update(zip([c["sha1"] for c in new], embed([c["embed_text"] for c in new]) if new else []))
        cache = {c["sha1"]: cache[c["sha1"]] for c in cs}
        INDEX.write_text(json.dumps(cache))
        print(f"index: {len(cs)} chunks from {len(files())} files, {len(new)} embedded now")
    for c in cs:
        c["vec"] = cache[c["sha1"]]
    df = {}
    for c in cs:
        for w in words(c["text"]):
            df[w] = df.get(w, 0) + 1
    IDF.clear()
    IDF.update({w: math.log(len(cs) / n) for w, n in df.items()})
    global IDF_MAX
    IDF_MAX = math.log(len(cs))
    return cs


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1)


def words(text):
    """Words of 4+ letters, acronyms (COP, ESP, PI) and every number, lower-cased, stop words out."""
    return {w.lower() for w in re.findall(r"\w+(?:\.\d+)?", text)
            if (len(w) >= 4 or w[0].isdigit() or (w.isupper() and len(w) >= 2)) and w.lower() not in STOP}


def kind(file):
    return next((v for k, v in KIND.items() if file.startswith(k)), "note")


def keyword(question, text):
    """Rarity-weighted share of the question's words found in the chunk: "doublets" is in every note, "absorption" is not."""
    w = {x: IDF.get(x, IDF_MAX) for x in words(question)}
    return sum(v for x, v in w.items() if x in text.lower()) / sum(w.values()) if w else 0.0


def retrieve(question, cs):
    """The POOL closest by cosine, re-ranked by cosine + keywords + design-result bonus, at most PER_FILE chunks per file."""
    q = embed([QUERY_PREFIX + question])[0]
    for c in cs:
        c["cosine"] = cosine(q, c["vec"])
    pool = sorted(cs, key=lambda c: -c["cosine"])[:POOL]
    for c in pool:
        c["score"] = W_COSINE * c["cosine"] + (1 - W_COSINE) * keyword(question, c["text"]) + (BONUS if kind(c["file"]) == "design result" else 0.0)
    out, seen = [], {}
    for c in sorted(pool, key=lambda c: -c["score"]):
        if seen.get(c["file"], 0) < PER_FILE:
            out.append(c)
            seen[c["file"]] = seen.get(c["file"], 0) + 1
        if len(out) == K:
            break
    return out


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?\]])\s+", text.strip()) if s]


def cited(s):
    return [int(n) for c in CITE.findall(s) for n in c.split(",")]


def numbers(s):
    return NUMBER.findall(checker.TAG.sub("", CITE.sub("", s)))


def holds(hit, nums):
    """True when every number of the sentence appears in the note."""
    pool = NUMBER.findall(hit["embed_text"])
    return all(any(checker.close(x, p) for p in pool) for x in nums)


def repair(text, hits):
    """A sentence without a valid citation whose numbers all sit in one or two notes gets those notes cited; returns text, fixes."""
    out, fixed, seen = [], [], set()
    for s in sentences(text):
        key = re.sub(r"\W+", " ", CITE.sub("", s).lower()).strip()
        if key in seen:   # the model repeated itself; one copy is enough
            continue
        seen.add(key)
        nums, cites = numbers(s), cited(s)
        if nums and not any(1 <= n <= len(hits) and holds(hits[n - 1], nums) for n in cites):
            cands = [i for i, h in enumerate(hits, 1) if holds(h, nums)]
            if 1 <= len(cands) <= 2:
                s = CITE.sub("", s).rstrip() + "[" + ", ".join(map(str, cands)) + "]"
                fixed.append(s)
        out.append(s)
    return " ".join(out), fixed


def grounding(text, hits):
    """Problems: uncited sentences, citations out of range, numbers or words not found in the cited notes."""
    problems = []
    for s in sentences(text):
        cites = cited(s)
        if not cites and "not in the notes" not in s.lower():
            problems.append(f"no citation: {s}")
        if any(not 1 <= n <= len(hits) for n in cites):
            problems.append(f"citation out of range 1-{len(hits)}: {s}")
        ok = [hits[n - 1] for n in cites if 1 <= n <= len(hits)]
        nums = numbers(s)
        for x in nums:
            if cites and not any(holds(h, [x]) for h in ok):
                problems.append(f"number {x} not in the cited notes {cites}: {s}")
        content = {w for w in words(CITE.sub("", s)) if len(w) >= 6}
        if ok and not nums and content and not any(w in h["text"].lower() for w in content for h in ok):
            problems.append(f"no word of this sentence is in the cited notes {cites}: {s}")
    return problems


def answer(question, show=False):
    t0, records = time.time(), []
    hits = retrieve(question, index())
    problems, first, fixed = [], None, []
    if max(h["cosine"] for h in hits) < MIN_COSINE:
        text = "Not in the notes."
    else:
        context = "\n\n".join(f"[{i}] ({kind(h['file'])}) {h['file']} § {h['heading']}\n{h['text']}" for i, h in enumerate(hits, 1))
        msgs = [{"role": "user", "content": prompt("rag_answer").replace("{context}", context).replace("{question}", question)}]
        msg, rec = log.chat(msgs, temperature=0)
        records.append(rec)
        text, fixed = repair(msg["content"], hits)
        first = msg["content"]
        problems = grounding(text, hits)
        if problems:
            msgs += [{"role": "assistant", "content": text},
                     {"role": "user", "content": prompt("rag_recheck").replace("{problems}", "\n".join(problems))}]
            msg, rec = log.chat(msgs, temperature=0)
            records.append(rec)
            text, fixed2 = repair(msg["content"], hits)
            fixed += fixed2
            problems = grounding(text, hits)
    s = log.summary(records, show=False)
    tokens = {"calls": s["calls"], "prompt": s["prompt_tokens"], "completion": s["completion_tokens"], "seconds": round(time.time() - t0, 1)}
    sources = [{"n": i, "file": h["file"], "kind": kind(h["file"]), "heading": h["heading"], "cosine": round(h["cosine"], 3),
                "score": round(h["score"], 3),
                "text": h["text"]} for i, h in enumerate(hits, 1)]
    save(question, text, first, problems, sources, tokens, fixed)
    if show:
        print(text + "\n\nsources:" + "".join(f"\n  [{x['n']}] {x['file']} § {x['heading']} (cosine {x['cosine']:.2f})" for x in sources))
        print(f"problems: {len(problems)}" + "".join(f"\n  {p}" for p in problems))
        print(f"citations repaired by code: {len(fixed)}" + "".join(f"\n  {f}" for f in fixed))
        print(f"tokens: {tokens['calls']} calls, {tokens['prompt']} prompt, {tokens['completion']} completion, {tokens['seconds']} s")
    return {"answer": text, "sources": sources, "problems": problems, "tokens": tokens, "repaired": fixed}


def save(question, text, first, problems, sources, tokens, fixed=()):
    slug = re.sub(r"[^a-z0-9]+", "_", question.lower())[:40].strip("_")
    lines = [f"# RAG answer, {log.DEFAULT_MODEL}, embeddings {EMBED_MODEL}", "", f"**Question.** {question}", "", "## Answer", "", text, "",
             "Grounding problems: " + ("none" if not problems else "".join(f"\n- {p}" for p in problems)), "",
             "Citations repaired by code (the sentence's numbers sit in that note alone): "
             + ("none" if not fixed else "".join(f"\n- {f}" for f in fixed)), ""]
    if first is not None and first != text:
        lines += ["## First answer (before re-prompt)", "", first, ""]
    lines += ["## Sources", ""] + [f"### [{x['n']}] ({x['kind']}) {x['file']} § {x['heading']} "
                                   f"(cosine {x['cosine']:.3f}, score {x['score']:.3f})\n\n"
                                   f"```\n{x['text']}\n```\n" for x in sources]
    lines += ["## Tokens", "", f"{tokens['calls']} model calls, {tokens['prompt']} prompt tokens, {tokens['completion']} completion tokens, "
              f"{tokens['seconds']} s wall", ""]
    (log.RUNS / f"{datetime.now():%Y%m%d_%H%M%S}_rag_{slug}.md").write_text("\n".join(lines))


if __name__ == "__main__":
    if "--files" in sys.argv:
        print("\n".join(files()) + f"\n{len(files())} files")
    elif "--build" in sys.argv:
        index(rebuild=True)
    else:
        answer(" ".join(sys.argv[1:]) or "Why a heat pump and not a boiler?", show=True)
