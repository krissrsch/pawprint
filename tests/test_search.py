from pathlib import Path

import numpy as np

from pawprint.chunk import Chunk
from pawprint.search import keyword_ids, rrf, search
from pawprint.store import Store


def mk(text, session="s1", part=0):
    return Chunk(session, "demo", "2026-01-01T00:00:00Z", "t", False, part, text)


def test_rrf_prefers_items_ranked_by_both_lists():
    assert rrf([[1, 2, 3], [2, 3, 9]])[:2] == [2, 3]


def test_keyword_search_and_umlauts():
    s = Store(":memory:")
    s.replace_file("f", 1, 1.0, [mk("Wir fixen den Login Redirect"), mk("Über Größen und Müll", part=1)])
    assert len(keyword_ids(s, "login", 5)) == 1
    assert len(keyword_ids(s, "uber grossen", 5)) >= 1 or len(keyword_ids(s, "Über", 5)) == 1


def test_keyword_query_with_quotes_does_not_break_fts():
    s = Store(":memory:")
    s.replace_file("f", 1, 1.0, [mk("hello world")])
    assert keyword_ids(s, 'he said "hello" AND (world) OR *', 5)


def test_replace_file_reuses_embeddings_for_unchanged_text():
    s = Store(":memory:")
    s.replace_file("f", 1, 1.0, [mk("same text"), mk("old text", part=1)])
    for i, _ in s.unembedded():
        s.set_embeddings([i], np.ones((1, 4), dtype=np.float32))
    s.replace_file("f", 2, 2.0, [mk("same text"), mk("new text", part=1)])
    assert [t for _, t in s.unembedded()] == ["new text"]
    assert s.file_state("f") == (2, 2.0)


def test_replaced_chunks_leave_the_keyword_index():
    s = Store(":memory:")
    s.replace_file("f", 1, 1.0, [mk("alpha beta")])
    s.replace_file("f", 2, 2.0, [mk("gamma delta")])
    assert keyword_ids(s, "alpha", 5) == []
    assert len(search(s, "gamma", mode="keyword")) == 1


def test_windows_cover_the_whole_chunk_and_keep_the_header():
    from pawprint.chunk import STEP, WINDOW, windows

    body = "".join(chr(65 + i % 26) for i in range(1400))
    ws = windows("[proj | title]\n" + body)
    assert all(w.startswith("[proj | title]\n") for w in ws)
    covered = set()
    for n, w in enumerate(ws):
        covered.update(range(n * STEP, n * STEP + len(w.split("\n", 1)[1])))
    assert covered >= set(range(len(body)))
    assert all(len(w.split("\n", 1)[1]) <= WINDOW for w in ws)
    assert windows("short") == ["short"]


def test_vector_search_scores_a_chunk_by_its_best_window(monkeypatch):
    import pawprint.search as S

    s = Store(":memory:")
    s.replace_file("f", 1, 1.0, [mk("first"), mk("second", part=1)])
    a, b = [i for i, _ in s.unembedded()]
    # chunk a: one weak window; chunk b: a weak window and a perfect one
    s.set_embeddings([a, b], [np.array([[0.6, 0.8]]), np.array([[0.0, 1.0], [1.0, 0.0]])])
    monkeypatch.setattr(S, "embed_query", lambda q, model: np.array([1.0, 0.0], dtype=np.float32))
    assert S.vector_ids(s, "q", 2) == [b, a]


def test_window_cache_is_dropped_when_the_index_changes():
    s = Store(":memory:")
    s.replace_file("f", 1, 1.0, [mk("one")])
    (i,) = [i for i, _ in s.unembedded()]
    s.set_embeddings([i], [np.ones((2, 3))])
    assert s.windows(3)[1].shape == (2, 3)
    s.forget("f")
    assert len(s.windows(3)[0]) == 0
