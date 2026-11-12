"""Cross-encoder reranking: a second model reads question and passage together and orders the top hits."""
from __future__ import annotations

import os

RERANKER = os.environ.get("PAWPRINT_RERANKER", "jinaai/jina-reranker-v2-base-multilingual")

_cache: dict = {}


def _load(name: str):
    if name not in _cache:
        from fastembed.rerank.cross_encoder import TextCrossEncoder  # late: heavy, and only used for ask / --rerank

        # On CPUs with efficiency cores the default (all logical cores) waits on the slow ones: i7-13700F 20 s -> 10 s with 8.
        threads = os.environ.get("PAWPRINT_THREADS")
        from .store import models_dir

        _cache[name] = TextCrossEncoder(model_name=name, threads=int(threads) if threads else None, cache_dir=models_dir())
    return _cache[name]


def rerank(query: str, hits: list[dict], name: str = RERANKER, read=None) -> list[dict]:
    """The same hits, best first, each with its model score in h["score"]. Equal scores keep their incoming order.
    read(hit) -> the text the model reads (default: the whole chunk); the cost grows with its length."""
    if len(hits) < 2:
        return hits
    scores = [float(s) for s in _load(name).rerank(query, [read(h) if read else h["text"] for h in hits])]
    for h, s in zip(hits, scores):
        h["score"] = s
    order = sorted(range(len(hits)), key=lambda i: (-scores[i], i))
    return [hits[i] for i in order]
