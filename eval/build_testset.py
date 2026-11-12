"""Build a large retrieval test set from your own transcripts with `claude -p`.

For random chunks (stratified by project) Claude writes questions in different styles plus a verbatim
evidence quote from the chunk. A question counts as answered when a retrieved chunk contains that quote,
which keeps the set valid if chunking changes later and tolerates duplicated passages.

Usage: python eval/build_testset.py [chunks] [seed]
Output: eval/private/big_set.json (git-ignored: it is made of your private conversations).
Sends redacted excerpts to `claude -p` (your logged-in subscription), 8 excerpts per call.
"""
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pawprint.ask import AskError, run_claude
from pawprint.chunk import without_head
from pawprint.embed import DEFAULT_MODEL
from pawprint.store import Store, db_path

N = int(sys.argv[1]) if len(sys.argv) > 1 else 400
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 11
OUT = Path(__file__).parent / "private" / "big_set.json"
PER_PROJECT_CAP = 35
BATCH = 8
STYLES = ["paraphrase", "vague", "other_language", "keywords"]
PAIRS = [(STYLES[i], STYLES[j]) for i in range(4) for j in range(i + 1, 4)]

PROMPT = """You write test questions for a search engine over someone's old Claude Code chats.
Below are numbered excerpts. For EACH excerpt write exactly 2 questions, one per style given for it.
The person will ask these weeks later, from memory, so the question must be answerable from that excerpt.

Styles:
- paraphrase: a natural question in the excerpt's language, reworded. Avoid the excerpt's distinctive words; use synonyms and general terms.
- vague: short and informal, details missing, like "wie hab ich das mit dem Login gelöst?". Still only that excerpt answers it.
- other_language: a natural question in the OTHER language than the excerpt (German excerpt -> English question, English -> German).
- keywords: a search-box query of 2 to 5 words, no question grammar, the most distinctive terms.

Rules:
- Self-contained. Never say "in this excerpt", "the text", "above".
- "evidence": an EXACT contiguous quote copied from the excerpt (max 100 characters) that contains the answer. Copy character for character.
- Skip an excerpt (write nothing for it) if it holds no concrete fact a person could ask about.
Answer with a JSON array only, no prose: [{{"n": 1, "style": "...", "q": "...", "evidence": "..."}}, ...]

{excerpts}
"""


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def sample(store: Store) -> list[dict]:
    rows = store.db.execute(
        "SELECT id, session_id, project, part, hash, text FROM chunks WHERE sidechain=0 AND length(text) > 400"
    ).fetchall()
    keep = []
    for cid, sid, project, part, h, text in rows:
        body = without_head(text)
        letters = sum(c.isalpha() for c in body) / max(len(body), 1)
        if project in ("pawprint", "Websites") or "pawprint" in text.lower() or letters < 0.55:
            continue  # this project's chats contain the eval itself
        keep.append({"id": cid, "session_id": sid, "project": project, "part": part, "hash": h, "body": body})
    rng = random.Random(SEED)
    rng.shuffle(keep)
    per, out = {}, []
    for c in keep:
        if per.get(c["project"], 0) >= PER_PROJECT_CAP:
            continue
        per[c["project"]] = per.get(c["project"], 0) + 1
        out.append(c)
        if len(out) == N:
            break
    return out


def ask_batch(batch: list[dict], offset: int) -> list[dict]:
    parts = []
    for i, c in enumerate(batch, 1):
        a, b = PAIRS[(offset + i) % len(PAIRS)]  # rotate all style pairs so every style appears equally often
        c["styles"] = [a, b]
        parts.append(f"### Excerpt {i} (styles: {a}, {b})\n{c['body']}")
    prompt = PROMPT.format(excerpts="\n\n".join(parts))
    for attempt in range(2):
        try:
            raw = run_claude(prompt)
            data = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
            break
        except (AskError, ValueError):
            data = []
    items = []
    for d in data:
        try:
            c = batch[int(d["n"]) - 1]
            ev, q, style = str(d["evidence"]), str(d["q"]).strip(), str(d["style"])
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        if style not in c["styles"] or len(q) < 6 or norm(ev) not in norm(c["body"]) or len(norm(ev)) < 12:
            continue  # evidence must really be in the chunk, otherwise the question cannot be scored
        items.append({"q": q, "style": style, "evidence": ev, "session_id": c["session_id"],
                      "project": c["project"], "part": c["part"], "hash": c["hash"]})
    return items


def main() -> None:
    store = Store(db_path(DEFAULT_MODEL))
    chunks = sample(store)
    batches = [(chunks[i: i + BATCH], i) for i in range(0, len(chunks), BATCH)]
    print(f"{len(chunks)} chunks from {len({c['project'] for c in chunks})} projects, {len(batches)} calls")
    items: list[dict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for n, res in enumerate(pool.map(lambda b: ask_batch(*b), batches), 1):
            items += res
            if n % 10 == 0:
                print(f"  {n}/{len(batches)} calls, {len(items)} questions")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    by = {s: sum(1 for i in items if i["style"] == s) for s in STYLES}
    print(f"wrote {len(items)} questions to {OUT}\nby style: {by}")


if __name__ == "__main__":
    main()
