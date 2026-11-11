"""Index transcripts incrementally: re-read only files whose size or mtime changed."""
from __future__ import annotations

import os
from pathlib import Path

from .chunk import chunk_turn
from .embed import DEFAULT_MODEL, embed_passages
from .parse import longpath, parse_file
from .store import Store


def index(store: Store, root: Path, model: str = DEFAULT_MODEL, embed: bool = True, log=print) -> dict:
    n_files = n_changed = 0
    for f in sorted(root.rglob("*.jsonl")):
        st = os.stat(longpath(f))
        n_files += 1
        if store.file_state(str(f)) == (st.st_size, st.st_mtime):
            continue
        chunks = [c for t in parse_file(f) for c in chunk_turn(t)]
        store.replace_file(str(f), st.st_size, st.st_mtime, chunks)
        n_changed += 1
    store.commit()
    todo = store.unembedded() if embed else []
    for i in range(0, len(todo), 64):
        batch = todo[i : i + 64]
        store.set_embeddings([b[0] for b in batch], embed_passages([b[1] for b in batch], model))
        store.commit()
        log(f"embedded {min(i + 64, len(todo))}/{len(todo)}")
    return {"files": n_files, "changed": n_changed, "embedded": len(todo)}
