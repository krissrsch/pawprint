"""Query expansion with Claude: a translation and a keyword version of the question.

Keyword search cannot cross languages and vague questions share few words with the answer. One short
`claude -p` call adds a translation (German <-> English) and 6-10 keywords; search then uses all three.
"""
from __future__ import annotations

import json
import os

from .ask import AskError, run_claude

# Haiku is enough for this small rewrite: same hit@10 as Sonnet on 798 questions, 2.4 s instead of 4.0 s, ~16x cheaper
EXPAND_MODEL = os.environ.get("PAWPRINT_EXPAND_MODEL", "haiku")

PROMPT = """You prepare search queries over someone's old programming chats (a mix of German and English: tools, games, apps).
For the question below write:
- "alt": the same question translated into the OTHER language. A German question becomes English, an English question becomes German; never repeat the question in its own language. Keep product names and code terms unchanged.
- "kw": one search-box string with 6 to 10 distinctive keywords that would appear in the answer text, in BOTH languages, with likely synonyms and technical terms. No question words.
Answer with one JSON object only: {{"alt": "...", "kw": "..."}}

Question: {question}
"""


def _run(prompt: str) -> str:
    return run_claude(prompt, EXPAND_MODEL)


def expand(question: str, runner=_run) -> dict | None:
    """{"alt": ..., "kw": ...}, or None when Claude is unavailable or answers garbage (search then runs without it)."""
    try:
        raw = runner(PROMPT.format(question=question))
        data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        alt, kw = str(data["alt"]).strip(), str(data["kw"]).strip()
    except (AskError, ValueError, KeyError, TypeError):
        return None
    return {"alt": alt, "kw": kw} if alt and kw else None
