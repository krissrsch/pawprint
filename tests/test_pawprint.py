from pathlib import Path

from pawprint.chunk import chunk_turn
from pawprint.parse import ParseStats, parse_file
from pawprint.redact import redact

FIX = Path(__file__).parent / "fixtures" / "invented.jsonl"


def test_parse_pairs_and_drops_noise():
    st = ParseStats()
    turns = parse_file(FIX, st)
    assert len(turns) == 3
    t = turns[0]
    assert t.user == "How do I fix the login redirect?"
    assert t.assistant == "Set the redirect URL in auth.py.\n\nDone, it works now."
    assert "TOOL OUTPUT" not in t.assistant and "hmm" not in t.assistant
    assert (t.project, t.branch, t.title) == ("demo-app", "main", "Fix login redirect")
    assert turns[1].user.startswith("Thanks")
    assert "ignore me" not in turns[1].user


def test_parse_counts_unknown_lines_without_crashing():
    st = ParseStats()
    parse_file(FIX, st)
    assert st.bad_lines == 1
    assert st.types["brand-new-kind"] == 1


def test_redact_patterns():
    assert "abcd1234efgh5678" not in redact("API_KEY=abcd1234efgh5678")
    assert "ghp_" not in redact("token ghp_" + "a" * 36)
    assert "hunter22" not in redact("postgres://bob:hunter22@db/x")
    assert "sk-ant-" not in redact("sk-ant-api03-" + "x" * 30)
    assert "BEGIN" not in redact("-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----")
    assert redact("plain sentence about tokens") == "plain sentence about tokens"


def test_chunk_redacts_and_splits():
    turns = parse_file(FIX)
    assert "abcd1234efgh5678" not in chunk_turn(turns[1])[0].text
    long = turns[0]
    long.assistant = "\n\n".join(f"para {i} " + "x" * 400 for i in range(10))
    chunks = chunk_turn(long, max_chars=1500)
    assert len(chunks) > 1
    assert all(len(c.text) <= 1500 for c in chunks)
    assert [c.part for c in chunks] == list(range(len(chunks)))


def test_chunk_single_giant_paragraph():
    turns = parse_file(FIX)
    turns[0].assistant = "y" * 5000
    assert all(len(c.text) <= 1500 for c in chunk_turn(turns[0]))


def test_slash_command_keeps_its_arguments():
    turns = parse_file(FIX)
    assert turns[2].user == "/dev continue with the demo"


def test_pasted_content_with_attributes_is_stripped():
    from pawprint.parse import _clean

    assert _clean("hi <pasted_content id=1>SECRET</pasted_content> x") == "hi  x"


def test_malformed_lines_are_counted_not_fatal():
    from pawprint.parse import parse_lines

    lines = [
        '{"type":"user","message":"just a string"}',
        '{"type":[1]}',
        '{"type":"user","cwd":5,"sessionId":7,"message":{"content":"hello"}}',
        '{"type":"assistant","message":{"content":[{"type":"text","text":42}]}}',
        '{"type":"ai-title","aiTitle":["x"]}',
    ]
    st = ParseStats()
    turns = parse_lines(lines, st)
    assert [t.user for t in turns] == ["hello"]
    assert turns[0].project == "" and turns[0].session_id == "" and turns[0].title == ""
    assert st.unknown_content >= 1 and st.types["<no type>"] == 1


def test_redact_more_token_shapes_and_odd_url_passwords():
    out = redact("postgres://bob:p@ss/word@db/x")
    assert "ss/word" not in out and "p@ss" not in out
    for secret in ["sk_live_" + "a" * 24, "rk_test_" + "b" * 24, "npm_" + "c" * 36,
                   "glpat-" + "d" * 20, "hf_" + "e" * 34, "sbp_" + "f" * 40]:
        assert secret not in redact(f"use {secret} here"), secret


def test_chunk_rejects_tiny_limits_and_redacts_titles():
    import pytest

    t = parse_file(FIX)[0]
    with pytest.raises(ValueError):
        chunk_turn(t, max_chars=100)
    t.title = "Rotate API_KEY=abcd1234efgh5678"
    assert "abcd1234efgh5678" not in chunk_turn(t)[0].title


def test_every_piece_carries_project_and_title_and_display_text_drops_it():
    from pawprint.chunk import without_head

    t = parse_file(FIX)[0]
    t.assistant = "\n\n".join(f"para {i} " + "x" * 400 for i in range(10))
    chunks = chunk_turn(t)
    assert len(chunks) > 1
    assert all(c.text.startswith("[demo-app | Fix login redirect]\n") for c in chunks)
    assert all(len(c.text) <= 1500 for c in chunks)
    assert without_head(chunks[0].text).startswith("User: How do I fix")
    assert without_head("no header here\nsecond line") == "no header here\nsecond line"
    assert without_head("[not | a header") == "[not | a header"
