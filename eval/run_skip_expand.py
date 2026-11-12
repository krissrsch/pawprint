"""S4: when can `ask` skip the Haiku rewrite? Measures, on the whole big test set, how often the quote is among the
20 candidates the reranker reads, with and without the rewrite, split by a simple "the search is already sure" rule:
keyword search and vector search agree on the top chunk. No reranker and no Claude call needed (rewrites are cached).

    python eval/run_skip_expand.py
"""
import json
import re
from pathlib import Path

from pawprint.chunk import without_head
from pawprint.embed import DEFAULT_MODEL
from pawprint.search import keyword_ids, search, vector_ids
from pawprint.store import Store, db_path

HERE = Path(__file__).parent / "private"
items = json.loads((HERE / "big_set.json").read_text(encoding="utf-8"))
rewrites = json.loads((HERE / "rewrites.json").read_text(encoding="utf-8"))
store = Store(db_path(DEFAULT_MODEL))
norm = lambda t: re.sub(r"\s+", " ", t).strip().lower()

rows = []
for it in items:
    q, r = it["q"], rewrites.get(it["q"])
    if not r:
        continue
    ev = norm(it["evidence"])
    found = lambda hits: any(ev in norm(without_head(h["text"])) for h in hits)
    kw, vec = keyword_ids(store, q, 1), vector_ids(store, q, 1)
    sure = bool(kw) and kw == vec
    rows.append((sure, found(search(store, q, 20)), found(search(store, q, 20, extra=[r["alt"], r["kw"]])), it["style"]))

n = len(rows)
for label, sel in (("all", rows), ("sure (keyword top 1 == vector top 1)", [x for x in rows if x[0]]),
                   ("not sure", [x for x in rows if not x[0]])):
    m = len(sel) or 1
    print(f"{label:40} n={len(sel):4} ({len(sel) / n:.0%})  in top 20: plain {sum(x[1] for x in sel) / m:.2f}  "
          f"with rewrite {sum(x[2] for x in sel) / m:.2f}")
sure = [x for x in rows if x[0]]
print("lost by skipping on 'sure':", sum(1 for x in sure if x[2] and not x[1]), "gained:", sum(1 for x in sure if x[1] and not x[2]))
# what the rule would do overall: plain search where sure, rewrite elsewhere
print(f"rule overall in top 20: {sum((x[1] if x[0] else x[2]) for x in rows) / n:.3f} vs always rewrite {sum(x[2] for x in rows) / n:.3f}")
