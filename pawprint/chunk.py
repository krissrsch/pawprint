"""Turn conversation turns into search chunks."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .parse import Turn
from .redact import redact

MAX_CHARS = 1500
OVERLAP = 150


@dataclass
class Chunk:
    session_id: str
    project: str
    timestamp: str
    title: str
    sidechain: bool
    part: int  # index of this piece within its turn
    text: str


def _split(text: str, limit: int) -> list[str]:
    """Split at paragraph breaks into pieces <= limit; hard-cut paragraphs that are longer."""
    pieces: list[str] = []
    cur = ""
    for para in re.split(r"\n\s*\n", text):
        while len(para) > limit:  # one giant paragraph: cut it, keep a small overlap
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(para[:limit])
            para = para[limit - OVERLAP :]
        if cur and len(cur) + len(para) + 2 > limit:
            pieces.append(cur)
            # carry the tail of the previous piece so context is not lost at the cut
            cur = cur[-OVERLAP:] + "\n\n" + para if len(cur) > OVERLAP else para
            if len(cur) > limit:
                cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        pieces.append(cur)
    return pieces


def chunk_turn(turn: Turn, max_chars: int = MAX_CHARS) -> list[Chunk]:
    body = f"User: {turn.user}\n\nAssistant: {turn.assistant}" if turn.assistant else f"User: {turn.user}"
    body = redact(body)
    return [
        Chunk(turn.session_id, turn.project, turn.timestamp, turn.title, turn.sidechain, i, p)
        for i, p in enumerate(_split(body, max_chars))
    ]
