"""Score `ask` end to end: does it answer correctly with sources, and refuse when nothing fits?

Usage: python eval/run_ask_eval.py [questions.json]
Each item is {"q": question, "must": [substrings the answer has to contain], "answerable": false for
questions the history cannot answer}. The real set lives in eval/private/ (git-ignored).
Every question costs one `claude -p` call, so keep the set small.
"""
import json
import sys
import time
from pathlib import Path

from pawprint.ask import NOT_FOUND, AskError, ask
from pawprint.embed import DEFAULT_MODEL
from pawprint.search import search
from pawprint.store import Store, db_path

qfile = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "private" / "ask_questions.json")
items = json.loads(qfile.read_text(encoding="utf-8"))
store = Store(db_path(DEFAULT_MODEL))

rows, wrong, no_cite, false_nf, invented = [], 0, 0, 0, 0
for it in items:
    t0 = time.time()
    answerable = it.get("answerable", True)
    try:
        answer, sources = ask(it["q"], search(store, it["q"], 6))
    except AskError as e:
        sys.exit(f"claude failed: {e}")
    refused = answer.startswith("Nicht gefunden")
    cited = "[Quelle" in answer
    if answerable:
        ok = (not refused) and all(m.lower() in answer.lower() for m in it["must"])
        wrong += not ok
        false_nf += refused
        no_cite += (not refused) and not cited
    else:
        ok = refused
        invented += not refused
    rows.append((("ok " if ok else "BAD"), "answerable" if answerable else "no answer ",
                 "refused" if refused else ("cited" if cited else "no cite"), f"{time.time() - t0:.0f}s", it["q"][:60]))

for r in rows:
    print(" | ".join(r))
a = sum(1 for i in items if i.get("answerable", True))
print(f"\nanswerable: {a - wrong}/{a} correct, {false_nf} wrongly refused, {no_cite} without citation")
print(f"unanswerable: {len(items) - a - invented}/{len(items) - a} refused, {invented} answered anyway")
