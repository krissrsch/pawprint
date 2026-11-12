"""Index transcripts incrementally: re-read only files whose size or mtime changed."""
from __future__ import annotations

import os
from pathlib import Path

from .chunk import chunk_turn
from .embed import DEFAULT_MODEL, embed_passages
from .parse import longpath, parse_file
from .store import Store


def index(store: Store, root: Path, model: str = DEFAULT_MODEL, embed: bool = True, log=print) -> dict:
    root = Path(root).resolve()  # one key per file, whether the root was given relative or absolute
    n_files = n_changed = n_failed = n_removed = 0
    seen: set[str] = set()
    for f in sorted(root.rglob("*.jsonl")):
        key = str(f)
        seen.add(key)
        n_files += 1
        try:
            st = os.stat(longpath(f))
            if store.file_state(key) == (st.st_size, st.st_mtime):
                continue
            chunks = [c for t in parse_file(f) for c in chunk_turn(t)]
        except Exception as e:  # one locked or odd file must not stop the rest; it is retried next run
            n_failed += 1
            log(f"skipped {f.name}: {type(e).__name__}: {e}")
            continue
        store.replace_file(key, st.st_size, st.st_mtime, chunks)
        n_changed += 1
    # Claude Code prunes old sessions; drop what vanished, but only below this root
    prefix = str(root) + os.sep
    for path in store.known_files():
        if path.startswith(prefix) and path not in seen:
            store.forget(path)
            n_removed += 1
    store.commit()
    todo = store.unembedded() if embed else []
    for i in range(0, len(todo), 64):
        batch = todo[i : i + 64]
        store.set_embeddings([b[0] for b in batch], embed_passages([b[1] for b in batch], model))
        store.commit()
        log(f"embedded {min(i + 64, len(todo))}/{len(todo)}")
    return {"files": n_files, "changed": n_changed, "failed": n_failed, "removed": n_removed, "embedded": len(todo)}
