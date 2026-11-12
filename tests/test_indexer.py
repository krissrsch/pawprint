import json
import os

from pawprint.indexer import index
from pawprint.store import Store


def session(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"type": "user", "sessionId": path.stem, "cwd": "C:\\Work\\demo", "timestamp": "2026-01-01T10:00:00Z",
             "message": {"content": text}}]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def count(store):
    return store.db.execute("SELECT count(*) FROM chunks").fetchone()[0]


def test_vanished_transcripts_leave_the_index(tmp_path):
    root = tmp_path / "projects"
    session(root / "p" / "a.jsonl", "alpha question")
    session(root / "p" / "b.jsonl", "beta question")
    s = Store(":memory:")
    index(s, root, embed=False, log=lambda *_: None)
    assert count(s) == 2
    (root / "p" / "b.jsonl").unlink()
    r = index(s, root, embed=False, log=lambda *_: None)
    assert r["removed"] == 1 and count(s) == 1
    assert s.db.execute("SELECT count(*) FROM fts WHERE fts MATCH 'beta'").fetchone()[0] == 0


def test_other_roots_are_not_pruned(tmp_path):
    session(tmp_path / "one" / "a.jsonl", "alpha")
    session(tmp_path / "two" / "b.jsonl", "beta")
    s = Store(":memory:")
    index(s, tmp_path / "one", embed=False, log=lambda *_: None)
    index(s, tmp_path / "two", embed=False, log=lambda *_: None)
    assert count(s) == 2


def test_relative_and_absolute_root_do_not_duplicate(tmp_path, monkeypatch):
    session(tmp_path / "projects" / "p" / "a.jsonl", "alpha")
    s = Store(":memory:")
    index(s, tmp_path / "projects", embed=False, log=lambda *_: None)
    monkeypatch.chdir(tmp_path)
    index(s, "projects", embed=False, log=lambda *_: None)
    assert count(s) == 1


def test_one_unreadable_file_does_not_stop_the_run(tmp_path):
    root = tmp_path / "projects"
    session(root / "p" / "good.jsonl", "good question")
    (root / "p" / "broken.jsonl").mkdir()  # a folder with a .jsonl name: stat works, open fails
    s = Store(":memory:")
    logs = []
    r = index(s, root, embed=False, log=logs.append)
    assert r["failed"] == 1 and r["changed"] == 1 and count(s) == 1
    assert any("broken.jsonl" in line for line in logs)
    assert os.path.isdir(root / "p" / "broken.jsonl")
