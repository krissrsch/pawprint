# Plan: Pawprint als zweites Gehirn für Claude-Sitzungen

Gegrillt: ja (12.11.2026, alle Empfehlungen angenommen). S1 und S2 umgesetzt am 12.11.2026.

## Ziel

Claude soll in einer laufenden Sitzung schon Besprochenes selbst nachschlagen, statt es neu zu
recherchieren oder von dir neu erklärt zu bekommen. Das spart Tokens und Zeit. Heute kann nur
du Pawprint benutzen (Paw-Reiter in Nikki), und jede Frage kostet dort etwa 10.000 Tokens.

## Was das Video zeigt, und was davon passt

Video: „Build a Second Brain with Claude (FULL GUIDE)" von Brennan Wells (lLTlzJWa1Yo).

- Der Kern ist Ebene 1: zwei Claude-Projekte („Personal Advisor", „Business Advisor") mit je einem
  festen Master-Prompt, der Person, Ziele, Projekte, Stil und Regeln enthält. Ein Skill führt per
  Interview durch das Schreiben dieser Prompts.
- Das ist kein Suchsystem. Der Prompt steht bei jeder Anfrage komplett im Kontext. Spart Erklärzeit,
  aber nicht Tokens, und er veraltet.
- Das Video nennt selbst tiefere Ebenen (Firmengehirn), zeigt sie aber nicht.

Was du davon schon hast: die globale `CLAUDE.md` und das Memory-Verzeichnis sind genau dieser
Master-Prompt. Den Teil muss man nicht nachbauen.

Was fehlt und das Video nicht liefert: der Abruf auf Anfrage. Ein fester Prompt kann nur Kurzes
enthalten. Alles andere (warum SQLite, wie der Kanto-Stage-Fix lief, welche Befehle damals
funktionierten) steht in tausenden Chunks, die nur bei Bedarf geladen werden sollen. Das ist
Pawprints Stärke. Die beiden Ansätze ergänzen sich: Master-Prompt für das Stabile, Pawprint für das
Konkrete.

## Bewertung: umsetzbar, sinnvoll, realistisch?

- **Umsetzbar:** ja. Suche, Reranker, Schwärzung und Index gibt es. Neu ist nur der Zugang für Claude.
- **Sinnvoll:** ja, aber nur für Wiedererkennungsfragen („wie haben wir X gelöst"). Für neue Aufgaben
  bringt es nichts. Ob es netto Tokens spart, ist nicht gemessen. Ein Treffer kostet etwa 1.500
  Tokens; er lohnt sich, wenn er eine Recherche von mehreren tausend Tokens ersetzt.
- **Realistisch:** ja mit zwei Vorbehalten. (1) Alte Chats können falsch oder überholt sein (Beispiel:
  der ROM-Fall, in dem der Chat sich selbst korrigierte). Treffer müssen Datum und Projekt zeigen und
  gelten als Hinweis, nicht als Wahrheit. (2) Das Suchmodell braucht einige GB Speicher und Sekunden
  zum Laden, deshalb darf es nicht bei jedem Aufruf neu starten.

## Schritte

### S1: Suche für Claude, ohne eigenes Sprachmodell (größter Hebel)
- Neuer Befehl `pawprint recall "<frage>" -n 4`: gibt kompakte Auszüge aus (Datum, Projekt, Titel,
  ca. 600 Zeichen), keine Umformulierung durch Haiku, keine Antwort durch Sonnet. Claude formuliert
  die Anfrage selbst um. Reranker bleibt an.
- Zugang als MCP-Server (stdio), damit das Modell einmal pro Sitzung lädt und nicht bei jedem Aufruf.
  Alternative, falls MCP zu viel ist: `recall` fragt den schon laufenden `pawprint serve` über HTTP.
- Ausgabe schon beim Erzeugen auf eine Obergrenze (ca. 2.000 Tokens) kappen.
- Test: Unit-Test mit erfundenen Fixtures, Datenschutztest bleibt (keine echten Chats im Repo).
- Aufwand: klein bis mittel.

### S2: Claude dazu bringen, es zu nutzen
- Zwei bis drei Zeilen in der globalen `CLAUDE.md`: vor Neu-Recherche zu bereits Besprochenem erst
  `recall` fragen; Treffer mit Datum nennen; bei Widerspruch zur aktuellen Datei gilt die Datei.
- Kein SessionStart-Hook, der automatisch Kontext einkippt: das kostet bei jeder Sitzung Tokens, auch
  wenn nichts gebraucht wird.

### S3: Messen, ob es sich lohnt (vor allem Weiteren)
- 10 echte Wiedererkennungsaufgaben aus deinen Chats (Befehle, Entscheidungen, Fehlerursachen).
  Jede einmal mit und einmal ohne `recall`, Tokens und Zeit aus den Transkripten ablesen.
- Entscheidung danach: weiter mit S4/S5 oder lassen.

### S4: Paw-Reiter günstiger machen
- Antworten zwischenspeichern (gleiche Frage kostet beim zweiten Mal nichts).
- Haiku-Umformulierung überspringen, wenn die Stichwortsuche schon eindeutig trifft. Vorher an den 798
  Testfragen messen, wie viel Trefferqualität das kostet.

### S5: Entscheidungsnotizen (optional, erst nach S3)
- Beim Indexieren pro Sitzung eine kurze Notiz „Entscheidung / Grund / Datum" erzeugen und als eigene
  Chunk-Art ablegen. Kostet beim Erzeugen Haiku-Tokens, macht Treffer kürzer und treffsicherer.
- Nur bauen, wenn S3 zeigt, dass rohe Auszüge zu lang oder zu laut sind.

## Datenschutz
Auszüge sind bereits geschwärzt. Was `recall` liefert, landet im Kontext von Claude und damit bei
Anthropic, wie der Chat damals auch. Es kommen nur die gefundenen Auszüge mit, nie der ganze Index.
Echte Chats bleiben außerhalb des Repos.

## Entscheidungen (Grilling 12.11.2026)
1. MCP-Server (stdio, `pawprint mcp`) mit einem Werkzeug `recall`; dazu der CLI-Befehl `pawprint recall`,
   beide über dieselbe Funktion. Ohne MCP-SDK, die vier nötigen JSON-RPC-Methoden sind handgeschrieben.
2. Standard: nur das aktuelle Projekt (Ordnername, in dem Claude Code läuft); `all_projects=true` für alle.
   Ohne Chats im Projekt sagt die Ausgabe das und schlägt `all_projects` vor, sie schaltet nicht still um.
3. Obergrenze 2.000 Tokens (6.000 Zeichen), `n` 1 bis 8, Standard 4.
4. Jeder Treffer zeigt Datum, Projekt, Titel, Sitzung; Kopfzeile „Hinweis, kein Beleg; die Datei gilt".
5. Regel in der globalen `CLAUDE.md`, Registrierung per `claude mcp add --scope user`.

## Ergebnis S1/S2 (12.11.2026)
- Ein Aufruf liefert bei 4 Treffern etwa 2.900 Zeichen (ca. 800 Tokens).
- Dauer: Der Reranker braucht auf dem i7-13700F etwa 20 s für 20 Kandidaten mit allen 24 Threads, mit
  `PAWPRINT_THREADS=8` (nur P-Kerne) etwa 10 s. Die 3,9 s aus eval/RESULTS.md wurden nicht erreicht.
  Kürzere Passagen (800 Zeichen) halbieren die Zeit, verändern aber die Reihenfolge; ob das die
  Qualität kostet, gehört in S3.
- Der Projektname kommt aus dem Arbeitsordner. Pawprint-Arbeit lief aus `Websites`, deshalb findet
  `recall` im Ordner `pawprint` nichts ohne `all_projects`.
- Es gibt keine Relevanzschwelle: `recall` liefert immer seine besten Treffer, auch wenn keiner passt.

## Reihenfolge
S1, S2, S3 (Messung), dann nach Ergebnis S4 und evtl. S5. Nach S1 und S2 Übersicht
`Zusammenfassungen & Erklärungen/pawprint.html` und README aktualisieren.
