"""Score retrieval on the big generated test set and write the failures down for analysis.

Usage: python eval/run_big_eval.py [questions.json] [model]
A question is answered at rank r when the r-th retrieved chunk contains the evidence quote.
Also reports session-level recall@5. Failures of the hybrid search go to eval/private/failures.json,
with what keyword search and vector search found on their own.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from pawprint.chunk import without_head
from pawprint.embed import DEFAULT_MODEL
from pawprint.search import keyword_ids, rrf, vector_ids
from pawprint.store import Store, db_path

HERE = Path(__file__).parent
qfile = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "private" / "big_set.json"
model = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MODEL
items = json.loads(qfile.read_text(encoding="utf-8"))
store = Store(db_path(model))
K = 30


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


texts: dict[int, dict] = {}


def chunk(cid: int) -> dict:
    if cid not in texts:
        c = store.get([cid])[cid]
        texts[cid] = {"body": norm(without_head(c["text"])), "session": c["session_id"], "raw": without_head(c["text"])}
    return texts[cid]


def rank_of(ids: list[int], ev: str, session: str):
    e = norm(ev)
    ev_rank = next((i for i, c in enumerate(ids, 1) if e in chunk(c)["body"]), None)
    seen = []
    for c in ids:
        s = chunk(c)["session"]
        if s not in seen:
            seen.append(s)
    s_rank = next((i for i, s in enumerate(seen[:10], 1) if s == session), None)
    return ev_rank, s_rank


results = []  # one dict per question with the ranks in each mode
for it in items:
    kw = keyword_ids(store, it["q"], 200)
    vec = vector_ids(store, it["q"], 200, model)
    modes = {"keyword": kw[:K], "vector": vec[:K], "hybrid": rrf([kw, vec])[:K]}
    results.append({"item": it, "ids": modes, "ranks": {m: rank_of(ids, it["evidence"], it["session_id"]) for m, ids in modes.items()}})


def metrics(rows, mode):
    n = len(rows) or 1
    ev = [r["ranks"][mode][0] for r in rows]
    sr = [r["ranks"][mode][1] for r in rows]
    return {
        "n": len(rows),
        "hit@1": sum(1 for x in ev if x == 1) / n,
        "hit@5": sum(1 for x in ev if x and x <= 5) / n,
        "hit@10": sum(1 for x in ev if x and x <= 10) / n,
        "mrr": sum(1 / x for x in ev if x) / n,
        "sess@5": sum(1 for x in sr if x and x <= 5) / n,
    }


def table(title, groups):
    print(f"\n== {title}")
    print(f"{'':22}{'n':>5} | " + " | ".join(f"{m:^31}" for m in ("keyword", "vector", "hybrid")))
    print(f"{'':27} | " + " | ".join(f"{'hit@1 hit@5 hit@10  mrr':^31}" for _ in range(3)))
    for name, rows in groups:
        cells = []
        for m in ("keyword", "vector", "hybrid"):
            x = metrics(rows, m)
            cells.append(f"{x['hit@1']:5.2f} {x['hit@5']:5.2f} {x['hit@10']:6.2f} {x['mrr']:6.2f}")
        print(f"{name:22}{len(rows):>5} | " + " | ".join(f"{c:^31}" for c in cells))


by_style = defaultdict(list)
by_part = defaultdict(list)
by_project = defaultdict(list)
for r in results:
    by_style[r["item"]["style"]].append(r)
    by_part["first piece" if r["item"]["part"] == 0 else "later piece"].append(r)
    by_project[r["item"]["project"]].append(r)

print(f"model {model}, {len(items)} questions from {len(by_project)} projects")
table("overall", [("all", results)])
table("by question style", sorted(by_style.items()))
table("by chunk position", sorted(by_part.items()))
top = sorted(by_project.items(), key=lambda kv: -len(kv[1]))[:6]
table("largest projects", top)

fails = []
for r in results:
    ev_rank = r["ranks"]["hybrid"][0]
    if ev_rank and ev_rank <= 10:
        continue
    it = r["item"]
    kind = ("keyword only" if r["ranks"]["keyword"][0] and r["ranks"]["keyword"][0] <= 10 else
            "vector only" if r["ranks"]["vector"][0] and r["ranks"]["vector"][0] <= 10 else
            "found late (11-30)" if ev_rank else "not in top 30")
    fails.append({**it, "kind": kind, "hybrid_rank": ev_rank, "retrieved": [
        {"project": store.get([c])[c]["project"], "text": chunk(c)["raw"][:160]} for c in r["ids"]["hybrid"][:3]]})
(HERE / "private" / "failures.json").write_text(json.dumps(fails, ensure_ascii=False, indent=1), encoding="utf-8")
kinds = defaultdict(int)
for f in fails:
    kinds[f["kind"]] += 1
print(f"\nhybrid misses at 10: {len(fails)} of {len(items)}  ->  eval/private/failures.json")
for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]):
    print(f"  {k}: {v}")
