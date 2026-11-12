"""Score the full question pipeline (translation + keywords, hybrid fusion, reranker) against plain hybrid search.

Usage: python eval/run_pipeline_eval.py [per_style=60 | failures] [candidates=20]
"failures" scores exactly the questions that plain hybrid search missed (eval/private/failures.json).
Uses a stratified sample of the big test set (per_style questions of each style), the cached rewrites from
eval/build_rewrites.py, and the real reranker, which takes about 4 s per question on a CPU.
"""
import json
import random
import re
import sys
import time
from pathlib import Path

from pawprint.chunk import without_head
from pawprint.embed import DEFAULT_MODEL
from pawprint.rerank import rerank
from pawprint.search import search
from pawprint.store import Store, db_path

HERE = Path(__file__).parent / "private"
only_failures = len(sys.argv) > 1 and sys.argv[1] == "failures"
per = 60 if only_failures or len(sys.argv) < 2 else int(sys.argv[1])
top = int(sys.argv[2]) if len(sys.argv) > 2 else 20
items = json.loads((HERE / "big_set.json").read_text(encoding="utf-8"))
rewrites = json.loads((HERE / "rewrites.json").read_text(encoding="utf-8"))
store = Store(db_path(DEFAULT_MODEL))

random.seed(5)
sample = []
for style in ("keywords", "paraphrase", "vague", "other_language"):
    xs = [i for i in items if i["style"] == style]
    random.shuffle(xs)
    sample += xs[:per]
if only_failures:
    sample = json.loads((HERE / "failures.json").read_text(encoding="utf-8"))


def rank(hits, evidence):
    e = re.sub(r"\s+", " ", evidence).strip().lower()
    return next((i for i, h in enumerate(hits, 1) if e in re.sub(r"\s+", " ", without_head(h["text"])).strip().lower()), None)


stages = {"plain hybrid": [], "+ translation & keywords": [], "+ translation, keywords & reranker": []}
by_style = {k: {s: [] for s in ("keywords", "paraphrase", "vague", "other_language")} for k in stages}
t0 = time.time()
for it in sample:
    q = it["q"]
    r = rewrites.get(q)
    extra = [r["alt"], r["kw"]] if r else []
    plain = search(store, q, 10)
    wide = search(store, q, top, extra=extra)
    deep = rerank(q, wide)
    for name, hits in zip(stages, (plain, wide[:10], deep[:10])):
        rk = rank(hits, it["evidence"])
        stages[name].append(rk)
        by_style[name][it["style"]].append(rk)
print(f"{len(sample)} questions, {time.time() - t0:.0f}s, rewrites for {sum(1 for i in sample if i['q'] in rewrites)} of them\n")


def line(label, ranks):
    n = len(ranks)
    return (f"{label:36} hit@1 {sum(1 for r in ranks if r == 1) / n:.2f}  hit@5 {sum(1 for r in ranks if r and r <= 5) / n:.2f}  "
            f"hit@10 {sum(1 for r in ranks if r and r <= 10) / n:.2f}  mrr {sum(1 / r for r in ranks if r) / n:.2f}")


for name, ranks in stages.items():
    print(line(name, ranks))
print("\nhit@10 by style (plain -> full pipeline):")
for style in ("keywords", "paraphrase", "vague", "other_language"):
    a, b = by_style["plain hybrid"][style], by_style["+ translation, keywords & reranker"][style]
    f = lambda rs: sum(1 for r in rs if r and r <= 10) / len(rs)
    print(f"  {style:16} {f(a):.2f} -> {f(b):.2f}")
