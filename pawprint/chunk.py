"""Turn conversation turns into search chunks."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .parse import Turn
from .redact import redact

MAX_CHARS = 1500
OVERLAP = 150
MAX_HEAD = 200  # the [project | title] line is cut to this length


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


WINDOW = 450  # about 120 tokens, what MiniLM reads before it truncates
STEP = 300


def windows(text: str) -> list[str]:
    """Overlapping slices of a chunk for embedding, each prefixed with the chunk's header line.
    The embedding model only reads ~128 tokens; without windows most of a 1,500-char chunk was invisible."""
    first, sep, rest = text.partition("\n")
    head = first if sep and first.startswith("[") and first.endswith("]") and " | " in first else ""
    body = rest if head else text
    starts = range(0, max(len(body) - (WINDOW - STEP), 1), STEP)
    return [(f"{head}\n{body[s:s + WINDOW]}" if head else body[s:s + WINDOW]) for s in starts]


def without_head(text: str) -> str:
    """The chunk text without its leading "[project | title]" line, for display."""
    first, sep, rest = text.partition("\n")
    return rest if sep and first.startswith("[") and first.endswith("]") and " | " in first else text


def chunk_turn(turn: Turn, max_chars: int = MAX_CHARS) -> list[Chunk]:
    if max_chars <= 2 * OVERLAP + MAX_HEAD:
        raise ValueError(f"max_chars must be larger than {2 * OVERLAP + MAX_HEAD}")  # smaller limits would loop or drop text
    body = f"User: {turn.user}\n\nAssistant: {turn.assistant}" if turn.assistant else f"User: {turn.user}"
    body = redact(body)
    title = redact(turn.title)  # titles are generated from the chat and can quote a secret too
    # every piece repeats project and title: later pieces of a long turn lose the question that gave them meaning
    head = (f"[{turn.project} | {title}]"[: MAX_HEAD - 1] + "\n") if (turn.project or title) else ""
    return [
        Chunk(turn.session_id, turn.project, turn.timestamp, title, turn.sidechain, i, head + p)
        for i, p in enumerate(_split(body, max_chars - len(head)))
    ]
