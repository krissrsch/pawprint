"""MCP server on stdio with one tool, `recall`, so a Claude Code session can look up earlier chats itself.
Claude Code starts it once per session, so the search models load once and stay loaded between calls.
Hand-written JSON-RPC: the tool needs four methods, not the MCP SDK and its dependencies."""
from __future__ import annotations

import json
import sys
from importlib.metadata import PackageNotFoundError, version

TOOL = {
    "name": "recall",
    "description": (
        "Search the user's earlier Claude Code chats for how something was already solved, decided or run "
        "(commands, reasons, causes of bugs). Use it before researching again something that was discussed "
        "before, not for new tasks. Returns dated excerpts; treat them as hints, the current files win. It adds to "
        "searching the project files, it does not replace it: check what a hit says about code in the files, and "
        "when nothing fits, go on searching the files. "
        "Searches the current project unless all_projects is true. Always fill `keywords`: the search matches words "
        "and meaning, so add the likely terms in German AND English, and file or tool names. If the first "
        "result misses, retry once with all_projects=true or other keywords. Each hit has an id: if an excerpt "
        "is cut off right where it matters, call again with more=<id> to read the whole passage and the next one."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to look for, in your own words (German or English)."},
            "keywords": {"type": "string", "description": "6 to 10 related words in German and English (translation of the query, synonyms, file or tool names)."},
            "n": {"type": "integer", "minimum": 1, "maximum": 8, "default": 4, "description": "Number of excerpts."},
            "all_projects": {"type": "boolean", "default": False, "description": "Search every project."},
            "project": {"type": "string", "description": "Project folder name to search instead of the current one."},
            "more": {"type": "integer", "description": "id of a hit: return that whole passage and the next one instead of searching."},
        },
        "required": [],
    },
}


def _version() -> str:
    try:
        return version("pawprint")
    except PackageNotFoundError:
        return "0"


def handle(msg: dict, run, here: str, more=None) -> dict | None:
    """One JSON-RPC message -> its response (None for notifications).
    run(query, n, project, keywords) -> text; more(chunk_id) -> text."""
    if "id" not in msg:
        return None
    mid, method = msg["id"], msg.get("method")
    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    if method == "initialize":
        # the one tool works the same in every protocol version so far, so take the client's
        result = {"protocolVersion": params.get("protocolVersion") or "2025-06-18", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "pawprint", "version": _version()}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [TOOL]}
    elif method == "tools/call" and params.get("name") == "recall":
        args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        q, n, cid = args.get("query"), args.get("n", 4), args.get("more")
        if more and isinstance(cid, int) and not isinstance(cid, bool):
            try:
                return _text(mid, more(cid))
            except Exception as e:
                return _text(mid, f"Lesen fehlgeschlagen: {type(e).__name__}: {e}", error=True)
        if not isinstance(q, str) or not q.strip():
            return _text(mid, "query fehlt.", error=True)
        if not isinstance(n, int) or isinstance(n, bool):
            n = 4
        project = None if args.get("all_projects") is True else (args.get("project") or here or None)
        kw = args.get("keywords")
        kw = kw.strip()[:500] if isinstance(kw, str) else ""
        try:
            return _text(mid, run(q.strip()[:500], n, project, kw))
        except Exception as e:  # a failed search is a tool error for Claude, not a dead server
            return _text(mid, f"Suche fehlgeschlagen: {type(e).__name__}: {e}", error=True)
    elif method == "tools/call":
        return _error(mid, -32602, f"unknown tool: {params.get('name')}")
    else:
        return _error(mid, -32601, f"method not found: {method}")
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _text(mid, text: str, error: bool = False) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}], "isError": error}}


def _error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def serve_stdio(run, here: str, inp=None, out=None, more=None) -> None:
    """Newline-delimited JSON-RPC on stdin/stdout until stdin closes."""
    if inp is None:
        sys.stdin.reconfigure(encoding="utf-8")  # Windows pipes default to the ANSI code page
        inp = sys.stdin
    if out is None:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        out = sys.stdout
        sys.stdout = sys.stderr  # a stray print from a library must not corrupt the protocol stream
    for line in inp:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
            resp = handle(msg, run, here, more) if isinstance(msg, dict) else _error(None, -32600, "invalid request")
        except ValueError:
            resp = _error(None, -32700, "parse error")
        if resp is not None:
            out.write(json.dumps(resp, ensure_ascii=False) + "\n")
            out.flush()
