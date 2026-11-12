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
from pawprint.recall import EXCERPT, MAX_CHARS, NOTE, recall
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
    assert out.count("\n[") == 8  # n is clamped to 8
    assert all(len(line) <= EXCERPT + 2 for line in out.splitlines())


def rpc(method, mid=1, **params):
    return {"jsonrpc": "2.0", "id": mid, "method": method, "params": params}


def test_mcp_handshake_list_and_call():
    calls = []

    def run(q, n, project):
        calls.append((q, n, project))
        return "treffer"

    init = handle(rpc("initialize", protocolVersion="2025-06-18", capabilities={}), run, "alpha")
    assert init["result"]["protocolVersion"] == "2025-06-18" and "tools" in init["result"]["capabilities"]
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, run, "alpha") is None
    assert handle(rpc("tools/list"), run, "alpha")["result"]["tools"] == [TOOL]

    res = handle(rpc("tools/call", name="recall", arguments={"query": " wie lief der Fix? "}), run, "alpha")
    assert res["result"] == {"content": [{"type": "text", "text": "treffer"}], "isError": False}
    handle(rpc("tools/call", name="recall", arguments={"query": "x", "n": 2, "all_projects": True}), run, "alpha")
    handle(rpc("tools/call", name="recall", arguments={"query": "x", "project": "beta", "n": "viele"}), run, "alpha")
    assert calls == [("wie lief der Fix?", 4, "alpha"), ("x", 2, None), ("x", 4, "beta")]


def test_mcp_errors_do_not_kill_the_server():
    def boom(q, n, project):
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
