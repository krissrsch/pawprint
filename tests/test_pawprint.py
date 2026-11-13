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


def test_redact_keeps_ordinary_words_after_secret_looking_names():
    for text in ["Save tokens: first, ranged reads", "secret_mew: befriend_species mew", "apiKeySource: none`)", "token: abcdefgh"]:
        assert redact(text) == text, text


def test_redact_still_masks_key_shaped_values_and_all_passwords():
    assert "aB3dE5gH7jK9mN1pQ3" not in redact("DISCORD_CLIENT_SECRET=aB3dE5gH7jK9mN1pQ3")
    assert "x7Qz9Lw2" not in redact('"api_key": "x7Qz9Lw2"')
    assert "correcthorse" not in redact("password: correcthorse")
    assert "Passwort123" not in redact("Passwort: Passwort123")
    assert "AbCdEfGhIjKlMnOpQrStUv" not in redact("auth_token=AbCdEfGhIjKlMnOpQrStUv")


def test_redact_shapes_found_in_the_security_review():
    cases = {
        "password is hunter2xyz": "hunter2xyz",
        'password: "my secret pass phrase"': "pass phrase",
        "Authorization: Basic dXNlcjpwYXNzd29yZA==": "dXNlcjpw",
        "ya29." + "a1B2c3D4e5" * 3: "a1B2c3D4e5",
        "SG." + "x" * 22 + "." + "y" * 43: "yyyyyyyy",
        "https://hooks.slack.com/services/T000/B000/XXXXXXXX": "T000/B000",
        "https://discord.com/api/webhooks/123456/abcDEF-ghi": "abcDEF",
        "DefaultEndpointsProtocol=https;AccountKey=abc123+/==;EndpointSuffix=core": "abc123",
        "pw=Sup3rSecret!": "Sup3rSecret",
        "Das Passwort ist Tr0mpete!": "Tr0mpete",
    }
    for text, secret in cases.items():
        assert secret not in redact(text), text
    for text in ("the password is required", "Das Passwort ist falsch.", "a pwa: progressive web app", "upwards: yes"):
        assert redact(text) == text, text


def test_claude_is_never_taken_from_the_current_folder(monkeypatch, tmp_path):
    import os

    from pawprint import ask

    here, real = tmp_path / "bin", tmp_path / "real"
    here.mkdir(), real.mkdir()
    monkeypatch.setenv("PATH", os.pathsep.join(["relative", str(here), str(real)]))
    # Windows: which() answers ".\claude.exe" for a file in the current folder, whatever path it was given
    monkeypatch.setattr(ask.shutil, "which", lambda cmd, path=None: ".\claude.exe" if path == str(here) else (str(real / "claude.exe") if path == str(real) else None))
    assert ask.find_claude() == str(real / "claude.exe")
    monkeypatch.setenv("PATH", "relative")
    assert ask.find_claude() is None
