import pytest
from fastapi.testclient import TestClient

from pawprint.ask import AskError
from pawprint.chunk import Chunk
from pawprint.store import Store
from pawprint.web import create_app

TOKEN = "t0ken"
H = {"X-Pawprint-Token": TOKEN}


def chunk(text, project, day, session):
    return Chunk(session, project, f"{day}T10:00:00Z", "title " + project, False, 0, text)


@pytest.fixture
def store():
    s = Store(":memory:")
    s.replace_file("a", 1, 1.0, [chunk("login redirect fix", "alpha", "2026-10-01", "s-a")])
    s.replace_file("b", 1, 1.0, [chunk("login token refresh", "beta", "2026-11-05", "s-b")])
    return s


def client(store, answer=lambda q, hits: ("ok [Quelle 1]", [])):
    return TestClient(create_app(store, TOKEN, answer=answer), base_url="http://127.0.0.1")


def test_token_required(store):
    c = client(store)
    assert c.get("/api/search", params={"q": "login"}).status_code == 401
    assert c.get("/api/search", params={"q": "login"}, headers={"X-Pawprint-Token": "nope"}).status_code == 401
    assert c.get("/api/projects").status_code == 401


def test_page_is_served_and_not_cached(store):
    r = client(store).get("/")
    assert r.status_code == 200 and "Pawprint" in r.text
    assert r.headers["cache-control"] == "no-store"


def test_foreign_host_is_refused(store):
    c = TestClient(create_app(store, TOKEN), base_url="http://evil.example")
    assert c.get("/", headers={"host": "evil.example"}).status_code == 403
    assert c.get("/api/projects", headers={**H, "host": "evil.example:8765"}).status_code == 403


def test_search_and_filters(store):
    c = client(store)
    both = c.get("/api/search", params={"q": "login", "mode": "keyword"}, headers=H).json()
    assert {h["project"] for h in both} == {"alpha", "beta"}
    only = c.get("/api/search", params={"q": "login", "mode": "keyword", "project": "beta"}, headers=H).json()
    assert [h["project"] for h in only] == ["beta"] and only[0]["date"] == "2026-11-05"
    late = c.get("/api/search", params={"q": "login", "mode": "keyword", "since": "2026-11-01"}, headers=H).json()
    assert [h["project"] for h in late] == ["beta"]
    early = c.get("/api/search", params={"q": "login", "mode": "keyword", "until": "2026-10-01"}, headers=H).json()
    assert [h["project"] for h in early] == ["alpha"]
    assert c.get("/api/search", params={"q": "login", "mode": "keyword", "project": "nope"}, headers=H).json() == []


def test_bad_input_is_rejected(store):
    c = client(store)
    assert c.get("/api/search", params={"q": "login", "since": "yesterday"}, headers=H).status_code == 422
    assert c.get("/api/search", params={"q": ""}, headers=H).status_code == 422
    assert c.get("/api/search", params={"q": "x", "mode": "evil"}, headers=H).status_code == 422


def test_projects_listed(store):
    assert set(client(store).get("/api/projects", headers=H).json()) == {"alpha", "beta"}


def test_ask_returns_answer_with_sources(store):
    seen = {}

    def fake(q, hits):
        seen["n"] = len(hits)
        return "Antwort [Quelle 1]", []

    r = client(store, fake).get("/api/ask", params={"q": "login"}, headers=H).json()
    assert r["answer"] == "Antwort [Quelle 1]" and seen["n"] >= 1 and r["sources"][0]["text"]


def test_ask_failure_becomes_502(store):
    def boom(q, hits):
        raise AskError("nicht eingeloggt")

    r = client(store, boom).get("/api/ask", params={"q": "login"}, headers=H)
    assert r.status_code == 502 and "nicht eingeloggt" in r.json()["detail"]
