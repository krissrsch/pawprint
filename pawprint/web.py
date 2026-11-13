"""Local web UI: search box, answers with clickable sources, filters. Binds to 127.0.0.1 only."""
from __future__ import annotations

import json
import re
import secrets
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .ask import AskError, ask
from .chunk import without_head
from .embed import DEFAULT_MODEL
from .expand import expand
from .rerank import rerank
from .search import search, smart_search
from .store import Store, text_hash

PAGE = Path(__file__).with_name("static") / "index.html"
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
CLAUDE_SLOTS = 2  # at most this many `claude -p` runs at once: each one costs tokens and a process


def create_app(store: Store, token: str, model: str = DEFAULT_MODEL, answer=ask, retrieve=None) -> FastAPI:
    """retrieve(q, allowed, lock) -> hits for questions; default is the full pipeline (translation + keywords + reranker)."""
    app = FastAPI(title="Pawprint", docs_url=None, redoc_url=None, openapi_url=None)
    lock = threading.Lock()  # one sqlite connection is shared by the worker threads
    claude_slots = threading.BoundedSemaphore(CLAUDE_SLOTS)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # A page on another site can point its own domain at 127.0.0.1 (DNS rebinding): refuse foreign Host headers.
        if request.headers.get("host", "").rsplit(":", 1)[0] not in LOCAL_HOSTS:
            return JSONResponse({"error": "bad host"}, status_code=403)
        resp = await call_next(request)
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers.setdefault("Content-Security-Policy", "default-src 'self'")  # the page sets its own, with a nonce
        return resp

    def auth(request: Request) -> None:
        sent = request.headers.get("x-pawprint-token", "")
        # bytes, because compare_digest raises on non-ASCII str and that would be a 500 instead of a 401
        if not secrets.compare_digest(sent.encode("utf-8", "surrogateescape"), token.encode()):
            raise HTTPException(401, "missing or wrong token")

    def allowed_for(project: str, since: str, until: str):
        for d in (since, until):
            if d and not DATE.match(d):
                raise HTTPException(422, "dates must look like 2026-11-12")
        with lock:
            return store.allowed_ids(project or None, since or None, until or None)

    def run_search(q: str, n: int, mode: str, project: str, since: str, until: str) -> list[dict]:
        allowed = allowed_for(project, since, until)
        with lock:
            return search(store, q, n, mode, model, allowed=allowed)

    def deep(q: str, allowed, lock) -> list[dict]:
        return smart_search(store, q, 6, model, allowed=allowed, expand_fn=expand, rerank_fn=rerank, lock=lock)

    find = retrieve or deep

    def view(h: dict) -> dict:
        return {k: h[k] for k in ("project", "title", "session_id")} | {"date": h["ts"][:10], "text": without_head(h["text"])}

    @app.get("/")
    def page():
        # inline script and style only with this request's nonce, so injected markup cannot run
        nonce = secrets.token_urlsafe(16)
        csp = f"default-src 'self'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'"
        return HTMLResponse(PAGE.read_text(encoding="utf-8").replace("__NONCE__", nonce), headers={"Content-Security-Policy": csp})

    @app.get("/api/projects", dependencies=[Depends(auth)])
    def projects():
        with lock:
            return store.projects()

    @app.get("/api/search", dependencies=[Depends(auth)])
    def api_search(q: str = Query(min_length=1, max_length=500), n: int = Query(10, ge=1, le=30),
                   mode: str = Query("hybrid", pattern="^(hybrid|keyword|vector)$"),
                   project: str = "", since: str = "", until: str = ""):
        return [view(h) for h in run_search(q, n, mode, project, since, until)]

    @app.get("/api/ask", dependencies=[Depends(auth)])
    def api_ask(q: str = Query(min_length=1, max_length=500), project: str = "", since: str = "", until: str = ""):
        # the same question with the same filters costs nothing the second time; any index change clears the saved answers
        key = text_hash(json.dumps([" ".join(q.lower().split()), project, since, until]))
        with lock:
            saved = store.saved_answer(key)
        if saved:
            return json.loads(saved)
        allowed = allowed_for(project, since, until)
        hits = [] if allowed == set() else find(q, allowed, lock)  # the slow steps run outside the lock
        if not claude_slots.acquire(blocking=False):
            raise HTTPException(429, "Es laufen schon zwei Fragen, bitte kurz warten.")
        try:
            text, used = answer(q, hits)
        except AskError as e:
            raise HTTPException(502, str(e)) from None
        finally:
            claude_slots.release()
        # same rule as the CLI: no source list next to "not found"
        result = {"answer": text, "sources": [view(h) for h in hits] if used else []}
        with lock:
            store.save_answer(key, json.dumps(result, ensure_ascii=False))
        return result

    return app


def pid_alive(pid: int) -> bool:
    """Is a process with this id still running? (os.kill(pid, 0) does not do that on Windows.)"""
    import os

    if os.name == "nt":
        import ctypes

        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = ctypes.c_void_p
        handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
        k32.CloseHandle(ctypes.c_void_p(handle))
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def exit_with(pid: int, every: float = 5.0) -> None:
    """Stop this process when `pid` is gone: a parent that crashed must not leave the search models in memory."""
    import os
    import time

    def watch() -> None:
        while pid_alive(pid):
            time.sleep(every)
        os._exit(0)

    threading.Thread(target=watch, daemon=True).start()


def serve(store: Store, model: str = DEFAULT_MODEL, port: int = 8765, root: Path | None = None, parent_pid: int | None = None) -> None:
    """root: transcripts folder to bring the index up to date before serving (None skips it).
    PAWPRINT_TOKEN fixes the token, so a parent process such as Nikki can talk to the server without
    putting the secret on a command line. parent_pid: exit when that process ends."""
    import os

    import uvicorn

    if parent_pid:
        exit_with(parent_pid)

    if root is not None:
        from .indexer import index

        try:
            r = index(store, root, model, log=lambda *_: None)
            print(f"Index aktuell: {r['changed']} von {r['files']} Dateien neu gelesen, {r['embedded']} Stücke eingebettet.", flush=True)
        except Exception as e:  # an old index is still better than no server
            print(f"Warnung: Index konnte nicht aktualisiert werden ({type(e).__name__}: {e}). Es wird der alte Stand benutzt.", flush=True)
    token = os.environ.get("PAWPRINT_TOKEN") or secrets.token_urlsafe(24)
    if len(token) < 16:
        raise SystemExit("PAWPRINT_TOKEN ist zu kurz (mindestens 16 Zeichen).")
    print(f"Pawprint läuft auf http://127.0.0.1:{port}/#token={token}", flush=True)
    print("Den Link nur lokal benutzen. Mit Strg+C beenden.", flush=True)
    uvicorn.run(create_app(store, token, model), host="127.0.0.1", port=port, log_level="warning", access_log=False)  # no URL (and so no question) in any log
