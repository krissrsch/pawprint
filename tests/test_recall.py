import io
import json
import os
import subprocess
import sys

import numpy as np
import pytest

import pawprint.search as S
from pawprint.chunk import Chunk
from pawprint.mcp_server import TOOL, handle, serve_stdio
from pawprint.recall import EXCERPT, MAX_CHARS, NOTE, excerpt, focus_words, more, recall
from pawprint.store import Store


def chunk(text, project="alpha", session="sess-0001", part=0):
    return Chunk(session, project, "2026-10-01T10:00:00Z", "Login fixen", False, part, f"[{project} | Login fixen]\n{text}")


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    # no embeddings in the fixtures, so the vector side finds nothing; this keeps the model from loading
    monkeypatch.setattr(S, "embed_query", lambda q, model: np.ones(4, dtype=np.float32))


@pytest.fixture
def store():
    s = Store(":memory:")
    s.replace_file("a", 1, 1.0, [chunk("User: login redirect kaputt\n\nAssistant: Cookie SameSite auf Lax gesetzt")])
    s.replace_file("b", 1, 1.0, [chunk("login token refresh im beta", project="beta", session="sess-0002")])
    return s


def test_recall_shows_date_project_title_and_drops_the_header(store):
    out = recall(store, "login redirect", project="alpha", rerank_fn=None)
    assert out.startswith(NOTE)
    assert "[1] 2026-10-01 · alpha · \"Login fixen\" · Sitzung sess-000" in out
    assert "SameSite auf Lax" in out and "[alpha | Login fixen]" not in out
    assert "beta" not in out.split("\n\n", 1)[1]  # the other project stays out


def test_recall_all_projects_and_unknown_project(store):
    assert "beta" in recall(store, "login token", project=None, rerank_fn=None)
    assert "all_projects=true" in recall(store, "login", project="gamma", rerank_fn=None)
    assert "Index ist leer" in recall(Store(":memory:"), "login", rerank_fn=None)


def test_recall_caps_each_excerpt_and_the_whole_output():
    s = Store(":memory:")
    s.replace_file("a", 1, 1.0, [chunk("login " + "x" * 3000, session=f"s{i}", part=i) for i in range(12)])
    out = recall(s, "login", n=99, project=None, rerank_fn=None)
    assert len(out) <= MAX_CHARS + 60
    assert 6 <= out.count("\n[") <= 8 and "Größengrenze" in out  # n is clamped to 8; the size cap drops the last ones
    assert all(len(line) <= EXCERPT + 4 for line in out.splitlines())


def rpc(method, mid=1, **params):
    return {"jsonrpc": "2.0", "id": mid, "method": method, "params": params}


def test_mcp_handshake_list_and_call():
    calls = []

    def run(q, n, project, kw):
        calls.append((q, n, project, kw))
        return "treffer"

    init = handle(rpc("initialize", protocolVersion="2025-06-18", capabilities={}), run, "alpha")
    assert init["result"]["protocolVersion"] == "2025-06-18" and "tools" in init["result"]["capabilities"]
    assert "condition" in init["result"]["instructions"]  # the hint for when to call recall goes into the system prompt
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, run, "alpha") is None
    assert handle(rpc("tools/list"), run, "alpha")["result"]["tools"] == [TOOL]

    res = handle(rpc("tools/call", name="recall", arguments={"query": " wie lief der Fix? "}), run, "alpha")
    assert res["result"] == {"content": [{"type": "text", "text": "treffer"}], "isError": False}
    handle(rpc("tools/call", name="recall", arguments={"query": "x", "n": 2, "all_projects": True}), run, "alpha")
    handle(rpc("tools/call", name="recall", arguments={"query": "x", "project": "beta", "n": "viele"}), run, "alpha")
    assert calls == [("wie lief der Fix?", 4, "alpha", ""), ("x", 2, None, ""), ("x", 4, "beta", "")]


def test_mcp_errors_do_not_kill_the_server():
    def boom(q, n, project, kw):
        raise RuntimeError("kaputt")

    assert handle(rpc("tools/call", name="recall", arguments={}), boom, "a")["result"]["isError"]
    assert "kaputt" in handle(rpc("tools/call", name="recall", arguments={"query": "q"}), boom, "a")["result"]["content"][0]["text"]
    assert handle(rpc("tools/call", name="other"), boom, "a")["error"]["code"] == -32602
    assert handle(rpc("nope"), boom, "a")["error"]["code"] == -32601
    out = io.StringIO()
    serve_stdio(boom, "a", io.StringIO("not json\n\n[1]\n" + json.dumps(rpc("ping", mid=7)) + "\n"), out)
    codes = [json.loads(l).get("error", {}).get("code") for l in out.getvalue().splitlines()]
    assert codes == [-32700, -32600, None]


def test_mcp_over_real_stdio_keeps_stdout_clean(tmp_path):
    msgs = [rpc("initialize", protocolVersion="2025-06-18", capabilities={}),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            rpc("tools/call", mid=2, name="recall", arguments={"query": "Größe ändern"})]
    env = os.environ | {"PAWPRINT_HOME": str(tmp_path)}  # empty index: answers without loading a model
    p = subprocess.run([sys.executable, "-m", "pawprint.cli", "mcp"], input="".join(json.dumps(m) + "\n" for m in msgs).encode(),
                       capture_output=True, env=env, timeout=120)
    lines = p.stdout.decode("utf-8").splitlines()
    assert [json.loads(l)["id"] for l in lines] == [1, 2]
    assert "Index ist leer" in json.loads(lines[1])["result"]["content"][0]["text"]


def test_excerpt_centres_on_the_words_of_the_question():
    body = "Einleitung " * 100 + "Der Cookie SameSite wurde auf Lax gesetzt, weil der Redirect sonst riss. " + "Schluss " * 100
    cut = excerpt("[p | t]\n" + body, focus_words("Warum SameSite Lax beim Redirect?"), 300)
    assert "SameSite wurde auf Lax" in cut and cut.startswith("… ") and cut.endswith(" …") and len(cut) <= 304
    assert excerpt("[p | t]\nkurz", ["kurz"], 300) == "kurz"
    assert excerpt("[p | t]\n" + "x" * 900, [], 300).startswith("x" * 300)  # no match: the start


def test_recall_passes_keywords_to_the_search(store):
    s = Store(":memory:")
    s.replace_file("a", 1, 1.0, [chunk("User: auth\n\nAssistant: we moved the session cookie to httponly")])
    assert "httponly" in recall(s, "Warum anders?", project=None, keywords="cookie httponly session", rerank_fn=None)


def test_recall_warns_when_the_best_hit_scores_low_but_keeps_the_hits(store):
    scored = lambda s: lambda q, hits: [h | {"score": s} for h in hits]
    weak = recall(store, "login", project=None, rerank_fn=scored(-0.5))
    assert "vermutlich nicht" in weak and "[1]" in weak
    assert "vermutlich nicht" not in recall(store, "login", project=None, rerank_fn=scored(0.5))


def test_recall_redacts_again_for_an_index_older_than_the_rules():
    s = Store(":memory:")
    s.replace_file("a", 1, 1.0, [chunk("login mit AccountKey=abc123+/== im String")])  # stored as an old index would have it
    out = recall(s, "login", project=None, rerank_fn=None)
    assert "abc123" not in out and "AccountKey=[REDACTED]" in out


def test_more_returns_the_whole_chunk_and_its_neighbours_from_the_same_file():
    s = Store(":memory:")
    s.replace_file("a", 1, 1.0, [chunk(f"teil {i} " + "y" * 900, part=i) for i in range(4)])
    s.replace_file("b", 1, 1.0, [chunk("anderes gespräch", project="beta")])
    ids = [r[0] for r in s.db.execute("SELECT id FROM chunks WHERE file='a' ORDER BY id")]
    out = more(s, ids[1])
    assert "teil 0" in out and "teil 1" in out and "teil 2" in out and "teil 3" not in out
    assert f"[id {ids[1]}] (gesuchtes Stück)" in out and "y" * 900 in out  # whole, not cut to an excerpt
    assert "anderes" not in more(s, ids[3]) and "Kein Stück" in more(s, 99999)


def test_mcp_more_reads_a_passage_without_a_query():
    got = handle(rpc("tools/call", name="recall", arguments={"more": 42}), lambda *a: "search", "a", more=lambda i: f"stück {i}")
    assert got["result"]["content"][0]["text"] == "stück 42"
    assert handle(rpc("tools/call", name="recall", arguments={"more": True}), lambda *a: "search", "a", more=lambda i: "x")["result"]["isError"]


def test_stop_hook_sends_a_giving_up_answer_back_once():
    from pawprint.stop_hook import decide

    gave_up = "Zum Aussehen beim ersten Besuch habe ich nichts gefunden, das kann ich also nicht sagen."
    assert decide({"stop_hook_active": False, "last_assistant_message": gave_up})["decision"] == "block"
    assert decide({"stop_hook_active": True, "last_assistant_message": gave_up}) is None  # second stop: let it end
    for fine in ("Die Datei liegt in `src/app.ts:12`. Nicht geprüft habe ich den Build.", "", None):
        assert decide({"stop_hook_active": False, "last_assistant_message": fine}) is None
    assert decide({"last_assistant_message": "I could not find where this is set."})["decision"] == "block"


def test_stop_hook_command_reads_stdin_and_answers_json():
    import subprocess

    def run(event):
        p = subprocess.run([sys.executable, "-m", "pawprint.cli", "stop-hook"], input=json.dumps(event),
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert p.returncode == 0, p.stderr
        return p.stdout

    assert json.loads(run({"stop_hook_active": False, "last_assistant_message": "Das weiß ich nicht."}))["decision"] == "block"
    assert run({"stop_hook_active": False, "last_assistant_message": "Erledigt."}) == ""
