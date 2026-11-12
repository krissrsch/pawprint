"""Ask Claude once to rewrite every test question (translation + keywords), 40 per call, into eval/private/rewrites.json
(or rewrites_<model>.json when a model other than sonnet is given: python eval/build_rewrites.py haiku).

run_pipeline_eval.py reads this cache so an evaluation does not need 800 claude calls each time.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pawprint.ask import AskError, run_claude

HERE = Path(__file__).parent / "private"
items = json.load(open(HERE / "big_set.json", encoding="utf-8"))
qs = [i["q"] for i in items]
BATCH = 40
MODEL = sys.argv[1] if len(sys.argv) > 1 else "sonnet"
OUT = "rewrites.json" if MODEL == "sonnet" else f"rewrites_{MODEL}.json"

PROMPT = """You prepare search queries over someone's old programming chats (a mix of German and English, tools, games, apps).
For EACH numbered question write:
- "alt": the same question translated into the OTHER language. A German question becomes English, an English question becomes German; never repeat the question in its own language. Keep product names and code terms unchanged.
- "kw": one search-box string with 6 to 10 distinctive keywords that would appear in the answer text, in BOTH languages, including likely synonyms and technical terms. No question words.
Answer with a JSON array only: [{{"n": 1, "alt": "...", "kw": "..."}}, ...]

{questions}
"""


def run(batch):
    start, chunk = batch
    text = "\n".join(f"{i}. {q}" for i, q in enumerate(chunk, 1))
    for _ in range(2):
        try:
            raw = run_claude(PROMPT.format(questions=text), MODEL)
            data = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
            return {chunk[int(d["n"]) - 1]: {"alt": str(d["alt"]), "kw": str(d["kw"])} for d in data}
        except (AskError, ValueError, KeyError, IndexError):
            pass
    return {}


batches = [(i, qs[i: i + BATCH]) for i in range(0, len(qs), BATCH)]
out = {}
with ThreadPoolExecutor(max_workers=3) as pool:
    for n, res in enumerate(pool.map(run, batches), 1):
        out.update(res)
        print(f"{n}/{len(batches)} calls, {len(out)} rewrites", flush=True)
(HERE / OUT).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("done", len(out), "of", len(qs))
