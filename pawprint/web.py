"""Local web UI: search box, answers with clickable sources, filters. Binds to 127.0.0.1 only."""
from __future__ import annotations

import re
import secrets
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from .ask import AskError, ask
from .chunk import without_head
from .embed import DEFAULT_MODEL
from .search import search
from .store import Store

PAGE = Path(__file__).with_name("static") / "index.html"
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def create_app(store: Store, token: str, model: str = DEFAULT_MODEL, answer=ask) -> FastAPI:
    app = FastAPI(title="Pawprint", docs_url=None, redoc_url=None, openapi_url=None)
    lock = threading.Lock()  # one sqlite connection is shared by the worker threads

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # A page on another site can point its own domain at 127.0.0.1 (DNS rebinding): refuse foreign Host headers.
        if request.headers.get("host", "").rsplit(":", 1)[0] not in LOCAL_HOSTS:
            return JSONResponse({"error": "bad host"}, status_code=403)
        resp = await call_next(request)
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'"
        return resp

    def auth(request: Request) -> None:
        sent = request.headers.get("x-pawprint-token", "")
        # bytes, because compare_digest raises on non-ASCII str and that would be a 500 instead of a 401
        if not secrets.compare_digest(sent.encode("utf-8", "surrogateescape"), token.encode()):
            raise HTTPException(401, "missing or wrong token")

    def run_search(q: str, n: int, mode: str, project: str, since: str, until: str) -> list[dict]:
        for d in (since, until):
            if d and not DATE.match(d):
                raise HTTPException(422, "dates must look like 2026-11-12")
        with lock:
            allowed = store.allowed_ids(project or None, since or None, until or None)
            return search(store, q, n, mode, model, allowed=allowed)

    def view(h: dict) -> dict:
        return {k: h[k] for k in ("project", "title", "session_id")} | {"date": h["ts"][:10], "text": without_head(h["text"])}

    @app.get("/")
    def page():
        return FileResponse(PAGE, media_type="text/html")

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
        hits = run_search(q, 6, "hybrid", project, since, until)
        try:
            text, used = answer(q, hits)
        except AskError as e:
            raise HTTPException(502, str(e)) from None
        # same rule as the CLI: no source list next to "not found"
        return {"answer": text, "sources": [view(h) for h in hits] if used else []}

    return app


def serve(store: Store, model: str = DEFAULT_MODEL, port: int = 8765) -> None:
    import uvicorn

    token = secrets.token_urlsafe(24)
    print(f"Pawprint läuft auf http://127.0.0.1:{port}/#token={token}")
    print("Den Link nur lokal benutzen. Mit Strg+C beenden.")
    uvicorn.run(create_app(store, token, model), host="127.0.0.1", port=port, log_level="warning")
