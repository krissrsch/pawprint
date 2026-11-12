"""Hybrid search: FTS5 keyword rank + vector rank, merged with Reciprocal Rank Fusion."""
from __future__ import annotations

import re

import numpy as np

from .embed import DEFAULT_MODEL, embed_query
from .store import Store

# 10, not the textbook 60: on 798 generated questions k=60 let deep, weak vector ranks push good keyword
# hits out of the top 10 (hit@10 0.56 -> 0.69 with k=10, see eval/RESULTS.md)
RRF_K = 10


def _fts_query(q: str) -> str:
    words = re.findall(r"\w{2,}", q)
    return " OR ".join(f'"{w}"' for w in words)


def keyword_ids(store: Store, q: str, n: int) -> list[int]:
    fq = _fts_query(q)
    if not fq:
        return []
    rows = store.db.execute("SELECT rowid FROM fts WHERE fts MATCH ? ORDER BY bm25(fts) LIMIT ?", (fq, n)).fetchall()
    return [r[0] for r in rows]


def vector_ids(store: Store, q: str, n: int, model: str = DEFAULT_MODEL) -> list[int]:
    qv = embed_query(q, model)
    owner, mat = store.windows(len(qv))
    if not len(owner):
        return []
    # a chunk scores by its best window (max-sim)
    chunk_ids, row_to_chunk = np.unique(owner, return_inverse=True)
    best = np.full(len(chunk_ids), -np.inf, dtype=np.float32)
    np.maximum.at(best, row_to_chunk, mat @ qv)
    top = np.argsort(-best)[:n]
    return [int(chunk_ids[i]) for i in top]


def rrf(rankings: list[list[int]], k: int = RRF_K) -> list[int]:
    score: dict[int, float] = {}
    for r in rankings:
        for pos, i in enumerate(r):
            score[i] = score.get(i, 0.0) + 1.0 / (k + pos + 1)
    return sorted(score, key=score.get, reverse=True)


def search(store: Store, q: str, limit: int = 8, mode: str = "hybrid", model: str = DEFAULT_MODEL, pool: int = 50,
           allowed: set[int] | None = None) -> list[dict]:
    """allowed: restrict to these chunk ids (filters apply before ranking, so the pool is widened)."""
    if allowed is not None:
        if not allowed:
            return []
        pool = max(pool, 20000)  # shortcut: filter after ranking, so rank (almost) everything; fine up to ~20k chunks, then filter in SQL
    rankings = []
    if mode in ("hybrid", "keyword"):
        rankings.append(keyword_ids(store, q, pool))
    if mode in ("hybrid", "vector"):
        rankings.append(vector_ids(store, q, pool, model))
    if allowed is not None:
        rankings = [[i for i in r if i in allowed] for r in rankings]
    top = rrf(rankings)[:limit]
    got = store.get(top)
    return [got[i] for i in top if i in got]
