"""Local embeddings (fastembed / ONNX, CPU). The model is swappable by name."""
from __future__ import annotations

import os

import numpy as np

DEFAULT_MODEL = os.environ.get("PAWPRINT_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

_cache: dict = {}


def _model(name: str):
    if name not in _cache:
        from fastembed import TextEmbedding  # imported late: slow, and not needed for keyword-only use

        _cache[name] = TextEmbedding(model_name=name)
    return _cache[name]


def _norm(vs) -> np.ndarray:
    a = np.asarray(list(vs), dtype=np.float32)
    return a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-9)


def embed_passages(texts: list[str], model: str = DEFAULT_MODEL) -> np.ndarray:
    return _norm(_model(model).passage_embed(texts))


def embed_query(text: str, model: str = DEFAULT_MODEL) -> np.ndarray:
    return _norm(_model(model).query_embed(text))[0]
