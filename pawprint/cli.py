"""pawprint command line. Only `stats` exists so far (M1)."""
from __future__ import annotations

import argparse
import time
from collections import Counter
from pathlib import Path

from .chunk import chunk_turn
from .parse import ParseStats, parse_file

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


def main() -> None:
    p = argparse.ArgumentParser(prog="pawprint", description="Ask your own Claude Code history")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stats", help="parse all transcripts and print counts")
    s.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    a = p.parse_args()
    if a.cmd == "stats":
        stats(a.root)


if __name__ == "__main__":
    main()
