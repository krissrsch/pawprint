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
