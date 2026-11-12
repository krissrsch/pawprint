"""pawprint command line: stats, index, search, ask, serve."""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

from .ask import AskError, ask
from .chunk import chunk_turn
from .embed import DEFAULT_MODEL
from .indexer import index
from .parse import ParseStats, parse_file
from .search import search
from .store import Store, db_path

DEFAULT_ROOT = Path.home() / ".claude" / "projects"


def stats(root: Path) -> None:
    t0 = time.time()
    files = sorted(root.rglob("*.jsonl"))  # includes <session>/subagents/*.jsonl
    st = ParseStats()
    turns = chunks = chars = failed = 0
    per_project: Counter = Counter()
    for f in files:
        try:
            ts = parse_file(f, st)
        except Exception as e:  # keep going; report at the end
            failed += 1
            print(f"FAILED {f.name}: {e}")
            continue
        for t in ts:
            cs = chunk_turn(t)
            turns += 1
            chunks += len(cs)
            chars += sum(len(c.text) for c in cs)
            per_project[t.project or f.parent.name] += len(cs)
    print(f"files: {len(files)} (failed: {failed})")
    print(f"lines: {st.lines} (unparsable: {st.bad_lines}, odd content: {st.unknown_content})")
    print(f"turns: {turns}  chunks: {chunks}  chars: {chars} (~{chars // 1_000_000} MB text)")
    print("line types:", ", ".join(f"{k}={v}" for k, v in st.types.most_common()))
    print("top projects (chunks):", ", ".join(f"{k}={v}" for k, v in per_project.most_common(8)))
    print(f"took {time.time() - t0:.1f}s")


def show(hits: list[dict], width: int = 300) -> None:
    for n, h in enumerate(hits, 1):
        body = " ".join(h["text"].split())[:width]
        print(f"[{n}] {h['ts'][:10]}  {h['project']}  '{h['title']}'  ({h['session_id'][:8]})\n    {body}\n")


def main() -> None:
    p = argparse.ArgumentParser(prog="pawprint", description="Ask your own Claude Code history")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stats", help="parse all transcripts and print counts")
    s.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    for name in ("index", "search", "ask", "serve"):
        x = sub.add_parser(name)
        x.add_argument("--model", default=DEFAULT_MODEL)
        if name == "serve":
            x.add_argument("--port", type=int, default=8765)
        elif name == "index":
            x.add_argument("--root", type=Path, default=DEFAULT_ROOT)
            x.add_argument("--no-embed", action="store_true", help="keyword index only")
        else:
            x.add_argument("query")  # ask reuses it as the question
            x.add_argument("-n", type=int, default=5)
            x.add_argument("--mode", choices=("hybrid", "keyword", "vector"), default="hybrid")
        if name == "ask":
            x.add_argument("--sources", type=int, default=6, help="how many excerpts go to Claude")
    a = p.parse_args()
    if a.cmd == "stats":
        stats(a.root)
    elif a.cmd == "index":
        t0 = time.time()
        print(index(Store(db_path(a.model)), a.root, a.model, embed=not a.no_embed), f"{time.time() - t0:.1f}s")
    elif a.cmd == "serve":
        from .web import serve  # imported late so the other commands start fast

        serve(Store(db_path(a.model)), a.model, a.port)
    elif a.cmd == "search":
        show(search(Store(db_path(a.model)), a.query, a.n, a.mode, a.model))
    else:
        hits = search(Store(db_path(a.model)), a.query, a.sources, a.mode, a.model)
        try:
            answer, sources = ask(a.query, hits)
        except AskError as e:
            sys.exit(f"Fehler: {e}")
        print(answer)
        print()
        for line in sources:
            print(line)


if __name__ == "__main__":
    main()
