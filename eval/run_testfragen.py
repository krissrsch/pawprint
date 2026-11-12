"""Answer the checklist questions with the real `ask` pipeline and compare with what the sources say.

Usage: python eval/run_testfragen.py
Needs eval/private/testfragen.json (python eval/make_testfragen.py). Each history question goes through
expansion, hybrid search, reranker and answer, exactly like `pawprint ask`; a second Claude call then compares
every answer with the expected source quote. The special questions are checked by code: refusals, no secret in
the answer, the public application id, the project and date filter, and the timing.
Result: eval/private/testfragen_result.json and a summary on screen.
"""
import json
import re
import sys
import time
from pathlib import Path

from pawprint.ask import NOT_FOUND, AskError, ask, run_claude
from pawprint.embed import DEFAULT_MODEL
from pawprint.expand import expand
from pawprint.rerank import rerank
from pawprint.search import smart_search
from pawprint.store import Store, db_path

HERE = Path(__file__).parent / "private"
entries = json.loads((HERE / "testfragen.json").read_text(encoding="utf-8"))
store = Store(db_path(DEFAULT_MODEL))

JUDGE = """You grade answers of a search tool over someone's old chats. For each numbered case compare the ANSWER with the EXPECTED source quote.
Verdicts:
- "passt": the answer states the fact the quote contains (same meaning is enough, wording may differ).
- "teils": it covers only part of it, or is vague, or mixes a correct fact with unsupported ones.
- "falsch": it states something that contradicts or is unrelated to the quote.
- "nichts": the answer says nothing was found ("Nicht gefunden").
Answer with a JSON array only: [{{"n": 1, "verdict": "passt", "why": "one short sentence"}}, ...]

{cases}
"""


def run_one(question: str) -> dict:
    t0 = time.time()
    hits = smart_search(store, question, 6, expand_fn=expand, rerank_fn=rerank)
    answer, sources = ask(question, hits)
    return {"answer": answer, "sources": sources, "seconds": round(time.time() - t0, 1),
            "refused": answer.startswith("Nicht gefunden")}


results = []
for n, e in enumerate(entries, 1):
    r = dict(e)
    try:
        if e["check"] == "filter":
            allowed = store.allowed_ids("Pokevivors", None, "2026-10-26")
            hits = smart_search(store, "Was haben wir als Letztes gemacht?", 6, allowed=allowed, expand_fn=expand, rerank_fn=rerank)
            bad = [h for h in hits if h["project"] != "Pokevivors" or h["ts"][:10] > "2026-10-26"]
            r.update(answer=f"{len(hits)} Fundstellen, davon {len(bad)} ausserhalb des Filters", verdict="passt" if hits and not bad else "falsch")
        elif e["check"] == "time":
            continue  # filled in from the timings below
        else:
            r.update(run_one(e["q"]))
            if e["check"] == "refuse":
                r["verdict"] = "passt" if r["refused"] and not r["sources"] else "falsch"
            elif e["check"] == "nokey":
                leaked = re.findall(r"[A-Za-z0-9_\-]{28,}", r["answer"])
                r["verdict"] = "falsch" if leaked else "passt"
            elif e["check"] == "appid":
                r["verdict"] = "passt" if "1568610877312077894" in r["answer"] else ("nichts" if r["refused"] else "teils")
    except AskError as ex:
        sys.exit(f"claude failed: {ex}")
    results.append(r)
    print(f"{n:2}/{len(entries)} {e['check']:7} {r.get('seconds', '-'):>5} s  {e['q'][:70]}", flush=True)

# one Claude call grades all history questions
judged = [r for r in results if r["check"] == "judge"]
cases = "\n\n".join(f"### Case {i}\nQUESTION: {r['q']}\nEXPECTED: {r['expect']}\nANSWER: {r['answer'][:900]}" for i, r in enumerate(judged, 1))
raw = run_claude(JUDGE.format(cases=cases))
for v in json.loads(raw[raw.index("["): raw.rindex("]") + 1]):
    judged[int(v["n"]) - 1].update(verdict=v["verdict"], why=v.get("why", ""))

times = [r["seconds"] for r in results if "seconds" in r]
timing = next(e for e in entries if e["check"] == "time")
results.append(dict(timing, answer=f"Mittel {sum(times) / len(times):.1f} s, langsamste {max(times):.1f} s",
                    verdict="passt" if sum(times) / len(times) <= 25 else "falsch"))
(HERE / "testfragen_result.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

tally = {}
for r in results:
    tally[r.get("verdict", "?")] = tally.get(r.get("verdict", "?"), 0) + 1
print("\nUrteile:", tally)
by = {}
for r in results:
    k = r["kind"]
    by.setdefault(k, []).append(r.get("verdict"))
for k, vs in by.items():
    print(f"  {k:26} passt {vs.count('passt')}/{len(vs)}")
print("\nNicht 'passt':")
for r in results:
    if r.get("verdict") != "passt":
        print(f"- [{r['kind']}] {r['q'][:80]}\n    {r.get('verdict')}: {r.get('why', '')} | Antwort: {r['answer'][:140]!r}")
