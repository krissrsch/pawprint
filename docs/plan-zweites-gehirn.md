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

## Ergebnis S3 (12.11.2026)
`eval/run_recall_eval.py`, 9 Fragen aus dem großen Testsatz, je eine frische `claude -p`-Sitzung (Sonnet, nur
Lesewerkzeuge) mit und ohne `recall`, von Hand nachgeprüft:
- Richtig: ohne 2, mit 4. Die beiden zusätzlichen Antworten stehen nur in Chats, nicht in Dateien.
- Kosten gleich (je ca. 0,05 $), Tokens mit `recall` eher mehr (46.000 statt 36.000), Zeit ca. 11 s mehr.
- `recall` hat keine Antwort verschlechtert.
- Fazit: Es spart keine Tokens, macht aber Wissen aus Chats erreichbar, zum gleichen Preis. Die Testfragen
  sind schwach (4 von 9 ohne Zusammenhang unbeantwortbar); echte Wiedererkennungsaufgaben wären fairer.

Entscheidung (Nutzer, 12.11.2026): erst `recall` verbessern, dann S4. Die Trefferquote muss steigen.

## recall verbessert (12.11.2026)
Gemessen mit `eval/run_recall_variants.py` (48 Fragen, Abrufebene):
- Stichwörter vom aufrufenden Claude (`keywords`, beide Sprachen) ersetzen die Haiku-Umformulierung kostenlos.
- Auszug 800 Zeichen um die Fragewörter statt der ersten 600: Die richtige Stelle steht im gezeigten Text in
  75 % statt 48 % der Fälle; unter den Top 4 in 88 % statt 75 %.
- Der Reranker liest nur 700 Zeichen um die Fragewörter: 3,2 statt 6,9 s. (Die ersten 700 Zeichen lesen
  kostete Treffer: 0,58. Verworfen.)
- Keine harte Relevanzschwelle, nur eine Warnung, wenn der beste Treffer schwach ist.
- `more=<id>` liest ein abgeschnittenes Stück ganz, mit Nachbarn.
- Regel: `recall` ergänzt die Dateisuche, ersetzt sie nicht.

In echten Sitzungen (12 Fragen, mit Werkzeug-Protokoll): 6 zu 6. Claude ruft `recall` nur bei 4 von 12 Fragen,
weil die meisten generierten Fragen aktuellen Code betreffen. Wo es `recall` für Chat-Wissen nutzt, gewinnt es;
Risiko sind veraltete Chats. Unterschiede von 2 bis 3 Fragen sind zwischen Läufen Rauschen. Für einen fairen Test
braucht es Wiedererkennungsfragen vom Nutzer selbst.

## S4 (12.11.2026)
- Antworten im Paw-Reiter werden gespeichert (Tabelle `answers` im Index); dieselbe Frage mit denselben Filtern
  kostet beim zweiten Mal nichts. Jede Index-Änderung leert den Speicher.
- Haiku überspringen, wenn Stichwort- und Vektorsuche denselben ersten Treffer haben: nur 13 % der Fragen,
  Ersparnis zu klein. Nicht gebaut (`eval/run_skip_expand.py`).

## Sicherheitsprüfung (12.11.2026)
Keine kritischen oder hohen Befunde in Pawprint und Nikki. Behoben: Schwärzungslücken (Basic-Auth, Google,
SendGrid, Slack/Discord-Webhooks, Azure, Passwörter in Anführungszeichen, `pw=`, „Passwort ist …“), `recall`
schwärzt erneut und markiert Auszüge als Daten, Modelle in `~/.pawprint/models` statt `%TEMP%`, Ordner/Index nur
für den Nutzer (POSIX), `secure_delete`, `claude -p` mit `--strict-mcp-config`, Token mindestens 16 Zeichen,
CI nur mit Leserechten, lokale Pfade aus dem Messskript. Nikki: Testschalter `NIKKI_E2E_PAW` nur noch in der
Entwicklung, CI nur mit Leserechten.

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
