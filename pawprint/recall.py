"""Compact excerpts for a Claude session: no rephrasing, no written answer, a hard size cap."""
from __future__ import annotations

from .chunk import without_head
from .embed import DEFAULT_MODEL
from .rerank import rerank
from .search import smart_search
from .store import Store

EXCERPT = 600  # characters per hit
MAX_CHARS = 6000  # ~2,000 tokens; German and code run at about 3 characters per token
MAX_N = 8
NOTE = "Hinweise aus früheren Chats, kein Beleg. Bei Widerspruch zur aktuellen Datei gilt die Datei."


def recall(store: Store, query: str, n: int = 4, project: str | None = None, model: str = DEFAULT_MODEL,
           rerank_fn=rerank) -> str:
    """project: search only this project's chats; None searches all of them."""
    n = max(1, min(int(n), MAX_N))
    if not store.db.execute("SELECT 1 FROM chunks LIMIT 1").fetchone():
        return "Der Pawprint-Index ist leer. Erst `pawprint index` laufen lassen."
    allowed = store.allowed_ids(project) if project else None
    if allowed == set():
        return f"Keine Chats aus dem Projekt '{project}' im Index. Mit all_projects=true alle Projekte durchsuchen."
    hits = smart_search(store, query, n, model, allowed=allowed, rerank_fn=rerank_fn)
    out = NOTE
    if project:
        out += f"\nDurchsucht: nur Projekt '{project}' (all_projects=true für alle)."
    if not hits:
        return out + "\nKeine Treffer."
    for i, h in enumerate(hits, 1):
        body = " ".join(without_head(h["text"]).split())
        if len(body) > EXCERPT:
            body = body[:EXCERPT] + " …"
        title = f" · \"{h['title'][:100]}\"" if h["title"] else ""
        entry = f"\n\n[{i}] {h['ts'][:10]} · {h['project']}{title} · Sitzung {h['session_id'][:8]}\n{body}"
        if len(out) + len(entry) > MAX_CHARS:
            out += "\n\n(weitere Treffer wegen der Größengrenze weggelassen)"
            break
        out += entry
    return out
