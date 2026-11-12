"""SQLite store: chunks, FTS5 keyword index, embeddings as float32 blobs."""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from pathlib import Path

import numpy as np

from .chunk import Chunk

SCHEMA = """
CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, size INTEGER, mtime REAL);
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY, file TEXT, session_id TEXT, project TEXT, ts TEXT, title TEXT,
  sidechain INTEGER, part INTEGER, text TEXT, hash TEXT, emb BLOB);
CREATE INDEX IF NOT EXISTS chunks_file ON chunks(file);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
  text, content='chunks', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
"""
COLS = ("id", "session_id", "project", "ts", "title", "sidechain", "part", "text")


def home() -> Path:
    return Path(os.environ.get("PAWPRINT_HOME", Path.home() / ".pawprint"))


def db_path(model: str) -> Path:
    """One database per embedding model, so models can be compared side by side."""
    return home() / ("index-" + re.sub(r"[^A-Za-z0-9]+", "-", model).strip("-") + ".db")


def text_hash(t: str) -> str:
    return hashlib.sha1(t.encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)  # the web server reads from worker threads
        self.db.executescript(SCHEMA)

    def file_state(self, path: str):
        return self.db.execute("SELECT size, mtime FROM files WHERE path=?", (path,)).fetchone()

    def replace_file(self, path: str, size: int, mtime: float, chunks: list[Chunk]) -> None:
        """Swap all chunks of one file. Embeddings of unchanged text are reused by hash."""
        d = self.db
        reuse = dict(d.execute("SELECT hash, emb FROM chunks WHERE file=? AND emb IS NOT NULL", (path,)))
        d.execute("INSERT INTO fts(fts, rowid, text) SELECT 'delete', id, text FROM chunks WHERE file=?", (path,))
        d.execute("DELETE FROM chunks WHERE file=?", (path,))
        for c in chunks:
            h = text_hash(c.text)
            cur = d.execute(
                "INSERT INTO chunks(file,session_id,project,ts,title,sidechain,part,text,hash,emb) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (path, c.session_id, c.project, c.timestamp, c.title, int(c.sidechain), c.part, c.text, h, reuse.get(h)),
            )
            d.execute("INSERT INTO fts(rowid, text) VALUES(?,?)", (cur.lastrowid, c.text))
        d.execute("INSERT OR REPLACE INTO files VALUES(?,?,?)", (path, size, mtime))

    def known_files(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT path FROM files")]

    def forget(self, path: str) -> None:
        """Drop a transcript that no longer exists, with its chunks and keyword entries."""
        self.db.execute("INSERT INTO fts(fts, rowid, text) SELECT 'delete', id, text FROM chunks WHERE file=?", (path,))
        self.db.execute("DELETE FROM chunks WHERE file=?", (path,))
        self.db.execute("DELETE FROM files WHERE path=?", (path,))

    def unembedded(self) -> list[tuple[int, str]]:
        return self.db.execute("SELECT id, text FROM chunks WHERE emb IS NULL").fetchall()

    def set_embeddings(self, ids: list[int], vecs: np.ndarray) -> None:
        self.db.executemany(
            "UPDATE chunks SET emb=? WHERE id=?", [(v.astype(np.float32).tobytes(), i) for i, v in zip(ids, vecs)]
        )

    def matrix(self) -> tuple[np.ndarray, np.ndarray]:
        """(ids, embedding matrix) of all embedded chunks.
        shortcut: rebuilt from SQLite on every query (~ms at 4k chunks); cache it on the Store above ~50k chunks."""
        rows = self.db.execute("SELECT id, emb FROM chunks WHERE emb IS NOT NULL").fetchall()
        if not rows:
            return np.zeros(0, dtype=np.int64), np.zeros((0, 0), dtype=np.float32)
        return np.array([r[0] for r in rows]), np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in rows])

    def get(self, ids: list[int]) -> dict[int, dict]:
        if not ids:
            return {}
        q = f"SELECT {','.join(COLS)} FROM chunks WHERE id IN ({','.join('?' * len(ids))})"
        return {r[0]: dict(zip(COLS, r)) for r in self.db.execute(q, ids)}

    def projects(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT project FROM chunks GROUP BY project ORDER BY count(*) DESC") if r[0]]

    def allowed_ids(self, project: str | None = None, since: str | None = None, until: str | None = None) -> set[int] | None:
        """Chunk ids matching the filters (dates as YYYY-MM-DD, inclusive); None means no filter."""
        where, args = [], []
        if project:
            where.append("project=?")
            args.append(project)
        if since:
            where.append("substr(ts,1,10)>=?")
            args.append(since)
        if until:
            where.append("substr(ts,1,10)<=?")
            args.append(until)
        if not where:
            return None
        return {r[0] for r in self.db.execute("SELECT id FROM chunks WHERE " + " AND ".join(where), args)}

    def commit(self) -> None:
        self.db.commit()
