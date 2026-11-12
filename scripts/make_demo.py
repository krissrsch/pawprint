"""Write a small set of invented Claude Code transcripts, for trying Pawprint and for the demo GIF.

Usage:
    python scripts/make_demo.py demo
    PAWPRINT_HOME=demo pawprint index --root demo/projects
    PAWPRINT_HOME=demo pawprint serve

Everything here is made up. No real session is involved.
"""
import json
import sys
import uuid
from pathlib import Path

# (project folder, date, title, [(user, assistant), ...])
SESSIONS = [
    ("recipe-app", "2026-09-03", "CORS error on login", [
        ("The frontend gets a CORS error when it calls /api/login. What's wrong?",
         "The API only allowed http://localhost:3000, but Vite runs on port 5173. I added "
         "http://localhost:5173 to ALLOWED_ORIGINS in api/settings.py and set allow_credentials=True, "
         "because the login sets a cookie. The error is gone and the login test passes."),
        ("Should we just allow all origins with * instead?",
         "No. With credentials the browser rejects * anyway, and it would let any website call the API "
         "with the user's cookie. Keep the explicit list and read it from the ALLOWED_ORIGINS environment "
         "variable in production."),
    ]),
    ("recipe-app", "2026-09-10", "SQLite or Postgres", [
        ("Do we need Postgres for the recipe app or is SQLite enough?",
         "SQLite is enough for now. There is one writer (the API process) and about 2,000 recipes. I turned on "
         "WAL mode so reads never block the writer. Switch to Postgres when a second process needs to write, "
         "for example a background importer."),
    ]),
    ("weather-cli", "2026-09-18", "429 from the weather API", [
        ("weather-cli keeps failing with HTTP 429 in the morning.",
         "The free plan allows 60 calls per hour and the status bar refreshes every 30 seconds from three "
         "terminals. I added a cache in ~/.cache/weather-cli that keeps each answer for 10 minutes, and on a "
         "429 the client now waits 2, 4 and 8 seconds before it gives up."),
    ]),
    ("portfolio", "2026-10-02", "Startseite lädt langsam", [
        ("Warum lädt die Startseite vom Portfolio so langsam?",
         "Das Hero-Bild war ein PNG mit 4,8 MB. Ich habe es als AVIF mit 180 KB exportiert, width und height "
         "gesetzt und es mit fetchpriority=high geladen. Der Largest Contentful Paint fällt in Lighthouse von "
         "4,1 s auf 1,3 s."),
    ]),
    ("home-automation", "2026-10-15", "Lights switch on at 3 am", [
        ("The hallway lights turn on at 3 am instead of 7 am. Why?",
         "The schedule compared the time against datetime.utcnow(), and the Raspberry Pi runs in UTC while "
         "the rules are written in local time. I changed it to datetime.now(ZoneInfo('Europe/Berlin')). It "
         "would also have broken at every switch to daylight saving time."),
        ("Can you add a test so this doesn't come back?",
         "Added tests/test_schedule.py with two fixed clocks, one in winter and one in summer time. Both "
         "check that the 07:00 rule fires at 07:00 Berlin time."),
    ]),
    ("recipe-app", "2026-10-28", "Deploy to Fly.io", [
        ("Deploy the recipe app to Fly.io.",
         "Deployed with fly launch and a volume for the SQLite file at /data. I set the secret with "
         "fly secrets set SECRET_KEY=demo-not-a-real-secret-123 and ALLOWED_ORIGINS to the production "
         "domain. The health check on /healthz is green."),
    ]),
    ("weather-cli", "2026-11-05", "CLI ohne Netz testen", [
        ("Wie teste ich den CLI-Aufruf, ohne das echte Netz zu benutzen?",
         "Mit respx: Es fängt die httpx-Aufrufe ab und gibt die gespeicherte Antwort aus "
         "tests/fixtures/berlin.json zurück. So laufen die Tests auch im Zug ohne WLAN und verbrauchen "
         "keine API-Aufrufe."),
    ]),
]


def lines(n: int, project: str, day: str, title: str, turns):
    sid = str(uuid.UUID(int=0xDE30 + n))  # stable, obviously fake ids
    cwd = f"C:\\Projects\\{project}"
    base = {"sessionId": sid, "cwd": cwd, "gitBranch": "main"}
    minute = 0
    for user, assistant in turns:
        ts = f"{day}T09:{minute:02d}:00Z"
        yield base | {"type": "user", "timestamp": ts, "message": {"role": "user", "content": user}}
        yield base | {"type": "assistant", "timestamp": ts,
                      "message": {"role": "assistant", "content": [{"type": "text", "text": assistant}]}}
        minute += 3
    yield {"type": "ai-title", "aiTitle": title, "sessionId": sid}


def main(target: str) -> None:
    root = Path(target) / "projects"
    for n, (project, day, title, turns) in enumerate(SESSIONS):
        folder = root / f"C--Projects-{project}"
        folder.mkdir(parents=True, exist_ok=True)
        rows = list(lines(n, project, day, title, turns))
        path = folder / f"{rows[0]['sessionId']}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"wrote {len(SESSIONS)} invented sessions to {root}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "demo")
