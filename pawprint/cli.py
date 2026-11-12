"""pawprint command line: stats, index, search, ask, serve."""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

from .ask import AskError, ask
from .chunk import chunk_turn, without_head
from .embed import DEFAULT_MODEL
from .indexer import index
from .parse import ParseStats, parse_file
from .expand import expand
from .rerank import rerank
from .search import search, smart_search
from .store import Store, db_path, home

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
        body = " ".join(without_head(h["text"]).split())[:width]
        print(f"[{n}] {h['ts'][:10]}  {h['project']}  '{h['title']}'  ({h['session_id'][:8]})\n    {body}\n")


def remember_exe() -> None:
    """Leave the launcher's path in ~/.pawprint/pawprint-path.txt, so a program that starts Pawprint (Nikki) finds it
    without a setting. Only a pawprint.exe next to this Python counts: that is what pip installed."""
    exe = Path(sys.executable).with_name("pawprint.exe")
    if not exe.is_file():
        return
    try:
        home().mkdir(parents=True, exist_ok=True)
        (home() / "pawprint-path.txt").write_text(str(exe), encoding="utf-8")
    except OSError:
        pass  # a read-only home only costs the convenience


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
            x.add_argument("--root", type=Path, default=DEFAULT_ROOT)
            x.add_argument("--no-index", action="store_true", help="do not bring the index up to date before serving")
            x.add_argument("--parent-pid", type=int, default=None, help="exit when this process ends (used by Nikki)")
        elif name == "index":
            x.add_argument("--root", type=Path, default=DEFAULT_ROOT)
            x.add_argument("--no-embed", action="store_true", help="keyword index only")
            x.add_argument("--reread", action="store_true", help="parse all transcripts again, e.g. after a redaction change; unchanged text keeps its vectors")
        else:
            x.add_argument("query")  # ask reuses it as the question
        if name == "search":
            x.add_argument("-n", type=int, default=5)
            x.add_argument("--mode", choices=("hybrid", "keyword", "vector"), default="hybrid")
            x.add_argument("--rerank", action="store_true", help="reorder the top 20 with a cross-encoder (slower, better)")
            x.add_argument("--expand", action="store_true", help="let Claude add a translation and keywords (one claude call)")
        if name == "ask":
            x.add_argument("--sources", type=int, default=6, help="how many excerpts go to Claude")
            x.add_argument("--no-expand", action="store_true", help="skip the translation/keyword step")
            x.add_argument("--no-rerank", action="store_true", help="skip the cross-encoder")
    a = p.parse_args()
    if a.cmd == "stats":
        stats(a.root)
    elif a.cmd == "index":
        remember_exe()
        t0 = time.time()
        print(index(Store(db_path(a.model)), a.root, a.model, embed=not a.no_embed, reread=a.reread), f"{time.time() - t0:.1f}s")
    elif a.cmd == "serve":
        remember_exe()
        from .web import serve  # imported late so the other commands start fast

        serve(Store(db_path(a.model)), a.model, a.port, None if a.no_index else a.root, a.parent_pid)
    elif a.cmd == "search":
        store = Store(db_path(a.model))
        if a.rerank or a.expand:  # the deep pipeline is always hybrid
            hits = smart_search(store, a.query, a.n, a.model, expand_fn=expand if a.expand else None,
                                rerank_fn=rerank if a.rerank else None)
        else:
            hits = search(store, a.query, a.n, a.mode, a.model)
        show(hits)
    else:
        hits = smart_search(Store(db_path(a.model)), a.query, a.sources, a.model,
                            expand_fn=None if a.no_expand else expand, rerank_fn=None if a.no_rerank else rerank)
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
