"""Score search modes on a golden set: Recall@5 and MRR at session level.

Usage: python eval/run_eval.py [model] [questions.json]
questions.json is a list of {"q": question, "s": session-id prefix}. The real set lives in
eval/private/ (git-ignored) because it is built from personal transcripts.
"""
import json
import sys
import time
from pathlib import Path

from pawprint.embed import DEFAULT_MODEL
from pawprint.search import search
from pawprint.store import Store, db_path

model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
qfile = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).parent / "private" / "questions.json")
questions = json.loads(qfile.read_text(encoding="utf-8"))
store = Store(db_path(model))

print(f"model: {model}, {len(questions)} questions")
for mode in ("keyword", "vector", "hybrid"):
    hit5 = rr = 0.0
    t0 = time.time()
    for item in questions:
        sessions = []
        for h in search(store, item["q"], limit=30, mode=mode, model=model):
            if h["session_id"] not in sessions:
                sessions.append(h["session_id"])
        rank = next((i for i, s in enumerate(sessions[:10], 1) if s.startswith(item["s"])), None)
        if rank:
            rr += 1 / rank
            hit5 += rank <= 5
    n = len(questions)
    print(f"{mode:8} recall@5={hit5 / n:.2f}  mrr={rr / n:.2f}  ({(time.time() - t0) / n * 1000:.0f} ms/query)")
