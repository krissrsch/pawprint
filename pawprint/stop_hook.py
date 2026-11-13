"""Claude Code Stop hook: when an answer gives up ("nicht gefunden", "kann ich nicht sagen") send the session back once
to ask `recall` first. Measured: sessions told so in the tool text and the server instructions still gave up after a few
greps on things that only a chat holds (eval/RESULTS.md). The hook only fires on giving up, so a normal answer costs
nothing; when recall was already asked, the session just repeats its answer once."""
from __future__ import annotations

import json
import re
import sys

GIVE_UP = re.compile(
    r"(habe ich (dazu )?nichts gefunden|nichts (dazu )?gefunden|nicht gefunden|nicht (herausfinden|klären|sagen|belegen|"
    r"beantworten|feststellen)|kann ich nicht sagen|weiß ich nicht|konnte ich nicht (finden|klären|herausfinden|belegen)|"
    r"keine (Angaben|Hinweise|Informationen|Belege) (dazu )?(gefunden|gibt)|could not (find|determine|tell)|"
    r"couldn't (find|determine|tell)|no (information|mention) (about|of)|not able to find)",
    re.I,
)
REASON = (
    "Du schreibst, dass du etwas nicht finden oder klären konntest. Betrifft die Frage etwas, das früher in diesem "
    "Projekt besprochen wurde, und hast du `recall` (MCP-Server pawprint) in dieser Antwort noch nicht gefragt, dann "
    "frag es jetzt einmal, mit keywords auf Deutsch und Englisch, und ergänze die Antwort mit Datum des Treffers. "
    "Sonst gib deine Antwort unverändert noch einmal aus."
)


def decide(event: dict) -> dict | None:
    """The hook's answer for one Stop event, or None to let the session stop."""
    if event.get("stop_hook_active"):  # we sent it back once already: never loop
        return None
    text = event.get("last_assistant_message")
    if not isinstance(text, str) or not GIVE_UP.search(text):
        return None
    return {"decision": "block", "reason": REASON}


def main() -> None:
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))  # Windows would read stdin as cp1252
    except ValueError:
        return  # never break a session over a malformed event
    out = decide(event) if isinstance(event, dict) else None
    if out:
        sys.stdout.write(json.dumps(out))  # ASCII escapes: right whatever code page the pipe has
