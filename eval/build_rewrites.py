"""Ask Claude once to rewrite every test question (translation + keywords), 40 per call, into eval/private/rewrites.json.

run_pipeline_eval.py reads this cache so an evaluation does not need 800 claude calls each time.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pawprint.ask import AskError, run_claude

HERE = Path(__file__).parent / "private"
items = json.load(open(HERE / "big_set.json", encoding="utf-8"))
qs = [i["q"] for i in items]
BATCH = 40

PROMPT = """You prepare search queries over someone's old programming chats (a mix of German and English, tools, games, apps).
For EACH numbered question write:
- "alt": the same question translated into the OTHER language (German -> English, English -> German), natural and keeping product names and code terms unchanged.
- "kw": one search-box string with 6 to 10 distinctive keywords that would appear in the answer text, in BOTH languages, including likely synonyms and technical terms. No question words.
Answer with a JSON array only: [{{"n": 1, "alt": "...", "kw": "..."}}, ...]

{questions}
"""


def run(batch):
    start, chunk = batch
    text = "\n".join(f"{i}. {q}" for i, q in enumerate(chunk, 1))
    for _ in range(2):
        try:
            raw = run_claude(PROMPT.format(questions=text))
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
(HERE / "rewrites.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("done", len(out), "of", len(qs))
