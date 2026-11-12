"""What does each recall change buy? Scores retrieval for the questions of the big test set (private).

Variants, all hybrid search + reranker, top 4 (what `recall` returns by default):
  A  before: reranker reads whole chunks, excerpt = first 600 characters, no keywords
  D  keywords (the cached rewrites stand in for the keywords the calling Claude writes), whole chunks,
     800-character excerpt centred on the words of question and keywords
  E  D, but the reranker reads only the 700 characters around those words
(An earlier run also tried a reranker that reads only the first 700 characters: hit@4 0.75 -> 0.58, dropped.)
Metrics: hit@4 = the quote is inside one of the 4 chunks; shown = the quote is inside the excerpt Claude actually sees.
Also prints the reranker's top score for hits vs misses, to pick a minimum score.

    python eval/run_recall_variants.py [per_style=12]
"""
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path

from pawprint.chunk import without_head
from pawprint.embed import DEFAULT_MODEL
from pawprint.recall import excerpt, focus_words
from pawprint.rerank import rerank
from pawprint.search import search
from pawprint.store import Store, db_path

HERE = Path(__file__).parent / "private"
per = int(sys.argv[1]) if len(sys.argv) > 1 else 12
items = json.loads((HERE / "big_set.json").read_text(encoding="utf-8"))
rewrites = json.loads((HERE / "rewrites.json").read_text(encoding="utf-8"))
store = Store(db_path(DEFAULT_MODEL))
random.seed(11)
sample = []
STYLES = ("keywords", "paraphrase", "vague", "other_language")
for style in STYLES:
    xs = [i for i in items if i["style"] == style and i["q"] in rewrites]
    random.shuffle(xs)
    sample += xs[:per]


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip().lower()


def seen(text: str, evidence: str) -> bool:
    return norm(evidence) in norm(text)


res = {v: {"hit": [], "shown": [], "t": [], "top": []} for v in "ADE"}
by_style = {v: {s: [] for s in STYLES} for v in "ADE"}
for n, it in enumerate(sample, 1):
    q, ev = it["q"], it["evidence"]
    r = rewrites[q]
    kw = f"{r['alt']} {r['kw']}"
    words = focus_words(q, kw)
    wide = search(store, q, 20, extra=[r["alt"], r["kw"]])
    runs = {
        "A": (search(store, q, 20), None, None),
        "D": (wide, None, kw),
        "E": (wide, lambda h: excerpt(h["text"], words, 700), kw),
    }
    for v, (cands, read, kws) in runs.items():
        t0 = time.time()
        top = rerank(q, [dict(h) for h in cands], read=read)[:4]
        dt = time.time() - t0
        hit = any(seen(without_head(h["text"]), ev) for h in top)
        if v == "A":
            shown = any(seen(" ".join(without_head(h["text"]).split())[:600], ev) for h in top)
        else:
            words = focus_words(q, kws)
            shown = any(seen(excerpt(h["text"], words), ev) for h in top)
        res[v]["hit"].append(hit)
        res[v]["shown"].append(shown)
        res[v]["t"].append(dt)
        if top and "score" in top[0]:
            res[v]["top"].append((top[0]["score"], hit))
        by_style[v][it["style"]].append(shown)
    if n % 8 == 0:
        print(f"{n}/{len(sample)}", flush=True)

N = len(sample)
print(f"\n{N} questions\n")
print("variant   hit@4  shown  rerank s/question")
for v, label in (("A", "before"), ("D", "keywords + centred excerpt"), ("E", "D, reranker reads 700 centred chars")):
    print(f"{v} {label:30} {sum(res[v]['hit']) / N:.2f}   {sum(res[v]['shown']) / N:.2f}   {statistics.mean(res[v]['t']):.1f}")
print("\nshown by style:")
for s in STYLES:
    print(f"  {s:15}", "  ".join(f"{v} {sum(by_style[v][s]) / len(by_style[v][s]):.2f}" for v in "ADE"))
for v in "DE":
    ok = sorted(s for s, h in res[v]["top"] if h)
    bad = sorted(s for s, h in res[v]["top"] if not h)
    q = lambda xs, p: f"{xs[int(p * (len(xs) - 1))]:.2f}" if xs else "-"
    print(f"\n{v}: top reranker score when the quote is in the top 4 (n={len(ok)}): p10 {q(ok, .1)} p50 {q(ok, .5)}; "
          f"when it is not (n={len(bad)}): p50 {q(bad, .5)} p90 {q(bad, .9)}")
