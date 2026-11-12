import pytest

from pawprint import rerank as R
from pawprint.ask import AskError
from pawprint.chunk import Chunk
from pawprint.expand import expand
from pawprint.search import CANDIDATES, search
from pawprint.store import Store


def mk(text, part=0):
    return Chunk("s1", "demo", "2026-01-01T00:00:00Z", "t", False, part, text)


@pytest.fixture
def store():
    s = Store(":memory:")
    s.replace_file("f", 1, 1.0, [mk("the cache keeps answers for ten minutes", 0), mk("Zwischenspeicher haelt Antworten zehn Minuten", 1),
                                 mk("unrelated notes about lunch", 2)])
    return s


def test_expand_parses_the_answer():
    out = expand("how long is the cache?", runner=lambda p: 'Sure: {"alt": "Wie lange ist der Cache?", "kw": "cache ttl Zwischenspeicher"}')
    assert out == {"alt": "Wie lange ist der Cache?", "kw": "cache ttl Zwischenspeicher"}


@pytest.mark.parametrize("raw", ["no json here", '{"alt": "only one"}', '{"alt": "", "kw": ""}', '["a"]', "{broken"])
def test_expand_gives_none_on_garbage(raw):
    assert expand("q", runner=lambda p: raw) is None


def test_expand_gives_none_when_claude_fails():
    def boom(p):
        raise AskError("not logged in")

    assert expand("q", runner=boom) is None


def test_extra_queries_widen_keyword_search(store):
    assert [h["text"] for h in search(store, "cache", 5, "keyword")] == ["the cache keeps answers for ten minutes"]
    both = search(store, "cache", 5, "keyword", extra=["Zwischenspeicher"])
    assert {h["part"] for h in both} == {0, 1}


def test_smart_search_pipeline_order(store, monkeypatch):
    import pawprint.search as S

    calls = []
    monkeypatch.setattr(S, "search", lambda st, q, limit, mode, model, allowed=None, extra=None: calls.append((q, limit, mode, extra)) or
                        [{"id": i, "text": f"t{i}"} for i in range(5)])
    out = S.smart_search(store, "q", 2, expand_fn=lambda q: {"alt": "a", "kw": "k"}, rerank_fn=lambda q, hits: hits[::-1])
    assert calls == [("q", CANDIDATES, "hybrid", ["a", "k"])]  # reranker needs a wide pool, expansion adds two queries
    assert [h["id"] for h in out] == [4, 3]                      # reranked first, then trimmed to the limit
    calls.clear()
    out = S.smart_search(store, "q", 2)                          # both steps off: plain hybrid, no wide pool
    assert calls == [("q", 2, "hybrid", [])] and [h["id"] for h in out] == [0, 1]


def test_smart_search_survives_a_failed_expansion(store, monkeypatch):
    import pawprint.search as S

    got = {}
    monkeypatch.setattr(S, "search", lambda st, q, limit, mode, model, allowed=None, extra=None: got.update(extra=extra) or [])
    S.smart_search(store, "q", 3, expand_fn=lambda q: None)
    assert got["extra"] == []


def test_rerank_orders_by_score_and_keeps_ties_stable(monkeypatch):
    class Fake:
        def rerank(self, query, docs):
            return [0.1, 0.9, 0.9, 0.5]

    monkeypatch.setattr(R, "_load", lambda name: Fake())
    hits = [{"text": c} for c in "abcd"]
    assert [h["text"] for h in R.rerank("q", hits)] == ["b", "c", "d", "a"]
    assert R.rerank("q", hits[:1]) == hits[:1]  # nothing to order, no model call
    assert R.rerank("q", []) == []


def test_web_ask_works_without_claude_or_reranker_being_available(store):
    from fastapi.testclient import TestClient

    from pawprint.web import create_app

    app = create_app(store, "tok", answer=lambda q, hits: ("A [Quelle 1]", ["x"]),
                     retrieve=lambda q, allowed, lock: search(store, q, 6, "keyword", allowed=allowed))
    r = TestClient(app, base_url="http://127.0.0.1").get("/api/ask", params={"q": "cache"}, headers={"X-Pawprint-Token": "tok"})
    assert r.status_code == 200 and r.json()["sources"]


def test_web_ask_with_empty_filter_never_calls_the_pipeline(store):
    from fastapi.testclient import TestClient

    from pawprint.web import create_app

    def boom(q, allowed, lock):
        raise AssertionError("expansion and reranker must not run for an empty filter")

    app = create_app(store, "tok", answer=lambda q, hits: ("Nicht gefunden", []), retrieve=boom)
    r = TestClient(app, base_url="http://127.0.0.1").get("/api/ask", params={"q": "cache", "project": "nope"},
                                                         headers={"X-Pawprint-Token": "tok"})
    assert r.status_code == 200 and r.json()["sources"] == []
