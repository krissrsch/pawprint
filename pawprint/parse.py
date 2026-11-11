"""Read Claude Code transcripts (.jsonl) into conversation turns.

The format is undocumented, so everything unknown is counted, never fatal.
Only user and assistant *text* is kept; tool output and thinking are dropped.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# Injected wrappers that are not something the user typed.
_NOISE = re.compile(
    r"<(system-reminder|local-command-caveat|local-command-stdout|command-name|"
    r"command-message|command-args|task-notification|pasted_content[^>]*)>.*?</\1>",
    re.S,
)


@dataclass
class Turn:
    """One user message plus the assistant text that answered it."""

    session_id: str
    project: str
    cwd: str
    branch: str
    timestamp: str
    title: str
    sidechain: bool
    user: str
    assistant: str


@dataclass
class ParseStats:
    lines: int = 0
    bad_lines: int = 0
    types: Counter = field(default_factory=Counter)
    unknown_content: int = 0  # user/assistant lines whose content had an unexpected shape


def _text(content) -> str | None:
    """Plain text of a message content, or None when it holds no text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(p for p in parts if p) or None
    return None


_CMD = re.compile(r"<command-name>(.*?)</command-name>", re.S)
_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)


def _clean(s: str) -> str:
    # "/dev do X" is stored as tags; the args are what the user actually asked, so keep them
    cmd, args = _CMD.search(s), _ARGS.search(s)
    prefix = f"{cmd.group(1).strip()} {args.group(1).strip() if args else ''}".strip() if cmd else ""
    body = _NOISE.sub("", s).strip()
    return f"{prefix} {body}".strip() if prefix else body


def project_name(cwd: str) -> str:
    return re.split(r"[/\\]", cwd.rstrip("/\\"))[-1] if cwd else ""


def parse_lines(lines: Iterator[str], stats: ParseStats | None = None) -> list[Turn]:
    stats = stats if stats is not None else ParseStats()
    turns: list[Turn] = []
    cur: Turn | None = None
    title = ""
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        stats.lines += 1
        try:
            d = json.loads(raw)
        except ValueError:
            stats.bad_lines += 1
            continue
        if not isinstance(d, dict):
            stats.bad_lines += 1
            continue
        t = d.get("type")
        stats.types[t] += 1
        if t == "ai-title":
            title = d.get("aiTitle") or title
            continue
        if t not in ("user", "assistant"):
            continue
        content = (d.get("message") or {}).get("content")
        text = _text(content)
        if text is None:
            # tool_result / thinking / tool_use only: expected, not an error
            if not isinstance(content, (list, str)):
                stats.unknown_content += 1
            continue
        text = _clean(text)
        if not text:
            continue
        if t == "user":
            if d.get("isMeta"):
                continue
            cur = Turn(
                session_id=d.get("sessionId", ""),
                project=project_name(d.get("cwd", "")),
                cwd=d.get("cwd", ""),
                branch=d.get("gitBranch", ""),
                timestamp=d.get("timestamp", ""),
                title="",
                sidechain=bool(d.get("isSidechain")),
                user=text,
                assistant="",
            )
            turns.append(cur)
        elif cur is not None:
            cur.assistant = f"{cur.assistant}\n\n{text}" if cur.assistant else text
    # the title line can come after the turns, so fill it in at the end
    for tr in turns:
        tr.title = title
    return turns


def longpath(path: str | Path) -> str:
    """Windows long-path prefix; session folders can exceed 260 characters."""
    p = str(Path(path).resolve())
    return chr(92) * 2 + "?" + chr(92) + p if len(p) > 240 and p[1:2] == ":" else p


def parse_file(path: str | Path, stats: ParseStats | None = None) -> list[Turn]:
    with open(longpath(path), encoding="utf-8", errors="replace") as f:
        return parse_lines(f, stats)
