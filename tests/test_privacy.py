"""Guard the public repo: no real transcripts, indexes or private eval questions may be committed."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# Real Claude Code transcripts carry UUID session ids and these fields; the invented fixtures do not.
REAL_TRANSCRIPT = re.compile(
    r'"sessionId"\s*:\s*"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"|"userType"\s*:\s*"external"'
)


def tracked() -> list[str]:
    if not shutil.which("git") or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def test_no_transcripts_indexes_or_private_files_are_tracked():
    bad = [
        p for p in tracked()
        if (p.endswith(".jsonl") and not p.startswith("tests/fixtures/"))
        or p.endswith((".db", ".sqlite", ".sqlite3"))
        or p.startswith("eval/private/")
    ]
    assert bad == []


def test_tracked_files_contain_no_real_transcript_lines():
    hits = []
    for p in tracked():
        f = ROOT / p
        if f.suffix in {".gif", ".png", ".jpg", ".ico"} or not f.is_file():
            continue
        if REAL_TRANSCRIPT.search(f.read_text(encoding="utf-8", errors="ignore")):
            hits.append(p)
    assert hits == [], f"looks like a real transcript: {hits}"
