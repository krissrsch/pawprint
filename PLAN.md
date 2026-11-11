Gegrillt: ja

# Plan: Pawprint

Stand 12.11.2026. Lokale Suche und Fragen über die eigenen Claude-Code-Gespräche. Untertitel: „Ask your own Claude Code history“. Der Name (gewählt am 12.11.2026) steht für die Spur, die deine Sitzungen hinterlassen, und passt zu Nikki.

## Ziel

Die Transkripte in `~/.claude/projects/` (bei dir: 2,5 GB, 239 Sitzungen, 50 Projektordner) durchsuchbar machen und Fragen in ganzen Sätzen beantworten, jede Antwort mit Quellen („Sitzung vom 10.11., Projekt notch-nikki“).

- **Nutzen für dich:** eigene Entscheidungen und Lösungen wiederfinden, statt sie neu zu erklären.
- **Nutzen zum Vorstellen:** ein echtes RAG-Projekt mit realen Daten: Parsing, Chunking, Embeddings, Hybrid-Suche, Quellen, Auswertung mit Testfragen. Dazu später eine Karte in Nikki.

## Entscheidungen (aus dem Gespräch)

| Frage | Entscheidung |
|---|---|
| Zielgruppe | zuerst du; so gebaut, dass es jeder mit einem Befehl starten kann |
| Sprache | Python für den Kern; Nikki bekommt später nur einen schmalen Anschluss |
| Antworten | Suche und Embeddings lokal; fertige Antwort über `claude -p` mit deinem Abo, kein API-Key; es gehen nur die gefundenen Textstellen raus |
| Läuft wo | **neben Nikki** als eigener lokaler Dienst auf 127.0.0.1 mit Token, nicht in Nikki. Nikki bekommt später nur eine Karte „Frag deine Geschichte“, die ihn aufruft; läuft er nicht, zeigt sie einen Hinweis mit „Starten“ |
| Ort | `C:\Programmieren\Tools\pawprint`, öffentliches GitHub-Repo `pawprint`, MIT |

## Was ich schon geprüft habe

- Zeilen in den Transkripten sind JSON mit `type`: `user`, `assistant` (Text in `message`), dazu viele andere Arten (`attachment`, `api-request`, `queue-operation` …). Der Großteil der 2,5 GB ist kein Gesprächstext, sondern Werkzeug-Ausgaben und API-Blobs. Die eigentliche Textmenge ist deutlich kleiner; sie wird in M1 gemessen.
- Pro Zeile stehen `sessionId`, `cwd`, `gitBranch`, `timestamp`; Sitzungstitel stehen als `ai-title`-Zeilen. Daraus kommen die Metadaten für die Quellenangaben.
- Python 3.13 ist da, aber keine ML-Bibliotheken. Eine RTX 4060 ist da (nur nötig, wenn ein größeres Embedding-Modell gewählt wird).
- Das Format ist nicht dokumentiert und kann sich ändern: der Parser muss tolerant sein und unbekannte Zeilen überspringen.

## Aufbau

```
pawprint/
├─ pawprint/
│  ├─ parse.py      Transkript-Zeilen -> Gesprächs-Turns mit Metadaten (tolerant)
│  ├─ redact.py     Geheimnisse (Schlüssel, Tokens, Passwörter) schwärzen
│  ├─ chunk.py      Turns -> Textstücke (Frage+Antwort, lange an Absätzen geteilt)
│  ├─ embed.py      lokale Embeddings (austauschbar)
│  ├─ store.py      SQLite: Chunks, FTS5-Index, Vektoren, Stand je Datei
│  ├─ search.py     Hybrid-Suche: Stichwort + Vektor, Zusammenführung per Reciprocal Rank Fusion
│  ├─ ask.py        gefundene Stellen + Frage -> `claude -p` -> Antwort mit [Quelle n]
│  ├─ cli.py        pawprint index | search | ask | stats
│  └─ web.py        kleine Oberfläche auf 127.0.0.1 (FastAPI + eine HTML-Seite)
├─ tests/           Unit-Tests mit erfundenen Beispiel-Transkripten (nie echte Chats)
├─ eval/            Testfragen (Golden Set) und Auswertung (Recall@5, MRR)
└─ README.md        Englisch, mit Diagramm, Demo-GIF, Auswertung
```

## Technik (Empfehlung, wird in M2 an Testfragen geprüft)

- **Parsen:** nur `user`- und `assistant`-Text, Werkzeug-Ausgaben weglassen (höchstens Werkzeugname und Dateipfad als Hinweis). Nebenketten (`isSidechain`) markieren.
- **Chunking:** ein Turn-Paar (Frage und Antwort) ist ein Stück; über etwa 1 500 Zeichen an Absätzen teilen, kleine Überlappung. Jedes Stück trägt Sitzung, Zeit, Projekt, Titel.
- **Embeddings:** ein kleines mehrsprachiges Modell (Deutsch und Englisch gemischt), zuerst per ONNX auf der CPU (z. B. über `fastembed`); Wechsel auf ein größeres Modell (z. B. bge-m3 auf der GPU), wenn die Auswertung es braucht. Genaue Modellnamen werden bei der Umsetzung gegen die Dokumentation geprüft.
- **Speicher:** eine SQLite-Datei mit FTS5 (Stichwortsuche) und den Vektoren als Blobs; Brute-Force-Suche reicht für einige zehntausend Stücke. `sqlite-vec` nur, wenn es zu langsam wird.
- **Inkrementell:** je Datei Größe und Stand merken, nur neue Zeilen lesen. Ein erster Lauf über alles, danach Sekunden.
- **Antworten:** `claude -p` mit den besten 6–8 Stücken; Prompt verlangt Zitate `[Quelle n]` und ein ehrliches „weiß ich nicht“, wenn nichts passt.
- **Datenschutz:** Schwärzen vor dem Index und noch einmal vor dem Senden; Projekte lassen sich ausschließen; alles lokal, nichts außer den gefundenen Stücken verlässt den PC.

## Meilensteine

| # | Ergebnis | Fertig, wenn |
|---|---|---|
| M1 | Parser, Schwärzen, Chunking, Messung der Textmenge | alle 239 Sitzungen laufen ohne Absturz durch; Zahlen zu Turns, Zeichen, Chunks; Unit-Tests grün |
| M2 | Embeddings, Speicher, Hybrid-Suche, `pawprint search` | 30 Testfragen aus echten Sitzungen: Recall@5 gemessen, Modell gewählt; zweiter Indexlauf in Sekunden |
| M3 | `pawprint ask` mit Quellen | Antworten zitieren Quellen, die stimmen; bei fehlender Information ehrliches „nicht gefunden“ |
| M4 | Oberfläche auf 127.0.0.1 | Suchfeld, Antwort mit anklickbaren Quellen, Filter nach Projekt und Zeitraum |
| M5 | Veröffentlichen | README mit Diagramm, Auswertung und Demo-GIF; CI auf GitHub; Übersicht in „Zusammenfassungen & Erklärungen“ |
| später | Nikki-Karte „Frag deine Geschichte“ | kleine lokale Schnittstelle, Karte in der Insel |

M1 bis M3 sind der Kern und die erste brauchbare Fassung (ungefähr ein Wochenende); M4 und M5 machen es vorzeigbar.

## Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Transkript-Format ändert sich | tolerant parsen, Beispiel-Transkripte als Testdaten, unbekannte Zeilen zählen statt abstürzen |
| Geheimnisse in alten Chats | Schwärzen mit Muster-Tests; Index nie ins Repo; `.gitignore` für Datenordner |
| Echte Chats im öffentlichen Repo | nur erfundene Fixtures; CI-Check, der nach `.jsonl` aus `~/.claude` sucht |
| Suche findet Falsches | Auswertung mit Testfragen, Hybrid statt nur Vektor, Quellen immer sichtbar |
| `claude -p` langsam oder nicht eingeloggt | verständliche Meldung; `search` funktioniert ohne Claude |
| Mehrsprachigkeit | Testfragen auf Deutsch und Englisch, Modell nach Messung wählen |

## Offen für die Umsetzung (keine Rückfrage nötig, nur zur Kenntnis)

- Python-Pakete (Kernbausteine, keine optionalen Extras): `fastembed` oder `sentence-transformers`, `numpy`, `fastapi`, `uvicorn`, `pytest`. Ich installiere sie in einer eigenen virtuellen Umgebung im Projektordner.
- Neues Repo: kleine Commits, Betreff im Imperativ, ohne Co-Authored-By.
