"""Write a checklist of ready-made test questions that fit your own conversations.

Usage: python eval/make_testfragen.py [seed]
Output: eval/private/testfragen.html (git-ignored: it quotes your private chats). Open it in a browser, ask each
question in `pawprint serve`, compare with what the source really says, tick a verdict, copy the result.

Questions come from the generated test set (eval/build_testset.py), but only those whose evidence quote occurs in
exactly one chunk (so the expected answer is unambiguous) and that come from sessions before today's work.
"""
import html
import json
import random
import re
import sys
from pathlib import Path

from pawprint.chunk import without_head
from pawprint.embed import DEFAULT_MODEL
from pawprint.store import Store, db_path

HERE = Path(__file__).parent / "private"
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 21
CUTOFF = "2026-11-11"  # sessions from the days this tool was built are in the index too and make tests too easy
PER_STYLE, PER_PROJECT = 7, 2
STYLE_LABEL = {"paraphrase": "umformuliert", "vague": "vage, aus dem Gedächtnis", "other_language": "andere Sprache",
               "keywords": "Stichwörter"}

store = Store(db_path(DEFAULT_MODEL))
chunks = store.db.execute("SELECT project, substr(ts,1,10), title, text FROM chunks").fetchall()


def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


bodies = [(p, d, t, norm(without_head(x))) for p, d, t, x in chunks]
items = json.loads((HERE / "big_set.json").read_text(encoding="utf-8"))
random.Random(seed).shuffle(items)

picked, per_project, per_style = [], {}, {}
for it in items:
    if per_style.get(it["style"], 0) >= PER_STYLE or per_project.get(it["project"], 0) >= PER_PROJECT:
        continue
    ev = norm(it["evidence"])
    hits = [(p, d, t) for p, d, t, b in bodies if ev in b]
    if len(hits) != 1 or hits[0][1] >= CUTOFF or len(it["q"]) < 18:
        continue  # ambiguous (several chunks hold the quote) or too recent
    p, d, t = hits[0]
    per_style[it["style"]] = per_style.get(it["style"], 0) + 1
    per_project[it["project"]] = per_project.get(it["project"], 0) + 1
    picked.append({"kind": STYLE_LABEL[it["style"]], "q": it["q"],
                   "expect": f"In der Quelle steht: „{it['evidence'].strip()}“",
                   "where": f"{d} · Projekt {p} · Sitzung „{t}“" if t else f"{d} · Projekt {p}"})
random.Random(seed).shuffle(picked)

special = [
    {"kind": "gibt es nicht", "q": "Wie backe ich eine Sachertorte nach Wiener Originalrezept?",
     "expect": "Richtig ist „Nicht gefunden“ und keine Quellenliste. Falsch: ein Rezept.", "where": "kommt in keinem Gespräch vor"},
    {"kind": "gibt es nicht", "q": "Was ist die Hauptstadt von Australien?",
     "expect": "Richtig ist „Nicht gefunden“. Claude kennt die Antwort, aber sie steht nicht in deinen Gesprächen.", "where": "Allgemeinwissen"},
    {"kind": "gibt es nicht", "q": "Welche Farbe hat mein Auto?",
     "expect": "Richtig ist „Nicht gefunden“. Falsch: eine erfundene Farbe.", "where": "kommt in keinem Gespräch vor"},
    {"kind": "Geheimnis", "q": "Welches Discord-Secret habe ich für die .env-Datei angegeben?",
     "expect": "Richtig: Das Secret erscheint nirgends im Klartext, höchstens als [REDACTED] oder der Hinweis, dass es nicht angezeigt wird. "
               "Falsch: irgendeine Zeichenfolge, die wie ein Schlüssel aussieht.",
     "where": "2026-11-07 · Projekt Black 2 on Discord"},
    {"kind": "Geheimnis", "q": "Welche Application ID habe ich für Discord genommen?",
     "expect": "Die Application ID ist öffentlich und darf stehen: 1568610877312077894. Prüfe, dass daneben kein Secret auftaucht.",
     "where": "2026-11-07 · Projekt Black 2 on Discord"},
    {"kind": "Filter", "q": "Was haben wir als Letztes gemacht?  (Filter: Projekt Pokevivors, bis 2026-10-26)",
     "expect": "Stelle in der Oberfläche den Projektfilter auf Pokevivors und „bis“ auf 26.10.2026 ein. "
              "Alle Fundstellen müssen zu Pokevivors gehören und dürfen nicht nach dem 26.10. liegen.",
     "where": "prüft die Filter"},
    {"kind": "Zeitgefühl", "q": "Wie lange dauert es, bis die Antwort da ist?  (Beliebige Frage mit „Fragen“)",
     "expect": "Erwartet sind 10 bis 20 Sekunden. Notiere die Zeit; deutlich mehr wäre ein Befund.", "where": "Geschwindigkeit"},
]
entries = picked + special

CARDS = []
for n, e in enumerate(entries, 1):
    CARDS.append(f"""<section class="card" data-n="{n}" data-q="{html.escape(e['q'], quote=True)}">
  <header><span class="num">{n}</span><span class="tag">{html.escape(e['kind'])}</span></header>
  <p class="q">{html.escape(e['q'])}</p>
  <details><summary>Erwartung anzeigen</summary><p>{html.escape(e['expect'])}</p><p class="where">{html.escape(e['where'])}</p></details>
  <div class="verdict" role="radiogroup" aria-label="Urteil zu Frage {n}">
    <label><input type="radio" name="v{n}" value="gut"> passt</label>
    <label><input type="radio" name="v{n}" value="teils"> teils</label>
    <label><input type="radio" name="v{n}" value="falsch"> falsch</label>
    <label><input type="radio" name="v{n}" value="nichts"> nichts gefunden</label>
    <input class="note" type="text" placeholder="Notiz (optional): was kam stattdessen?" aria-label="Notiz zu Frage {n}">
  </div>
</section>""")

PAGE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pawprint Testfragen</title>
<style>
:root{--bg:#0e0f12;--card:#17181d;--raised:#1f2027;--line:#2c2e37;--text:#ececf1;--muted:#a3a4b0;--accent:#a9e7bd;--ink:#10261a;--warn:#f5c76b;--blue:#8ab4ff}
@media (prefers-color-scheme: light){:root{--bg:#f6f6f3;--card:#fff;--raised:#f0f0ec;--line:#dcdce2;--text:#1b1c20;--muted:#5a5c66;--accent:#2f8f57;--ink:#fff;--warn:#a86a00;--blue:#2f62c9}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 "Segoe UI",system-ui,sans-serif}
main{max-width:820px;margin:0 auto;padding:28px 16px 90px}h1{margin:0 0 4px;font-size:26px}.lead{color:var(--muted);margin:0 0 16px}
ol.how{margin:0 0 22px;padding-left:20px;color:var(--muted)}ol.how b{color:var(--text)}
.bar{position:sticky;top:0;z-index:2;display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:10px 0;background:var(--bg);border-bottom:1px solid var(--line)}
.bar .count{color:var(--muted);flex:1}button{font:inherit;color:var(--text);background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 14px;cursor:pointer}
button.primary{background:var(--accent);color:var(--ink);border-color:transparent;font-weight:600}button:hover{filter:brightness(1.1)}
:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.card{margin-top:14px;padding:14px 16px;border:1px solid var(--line);border-radius:14px;background:var(--card)}
.card.done{border-color:var(--accent)}.card header{display:flex;gap:10px;align-items:center}.num{font-weight:700;color:var(--accent)}
.tag{padding:1px 9px;border-radius:99px;background:var(--raised);color:var(--muted);font-size:12px}
.q{margin:8px 0;font-size:17px;font-weight:600}details{margin:6px 0 10px}summary{cursor:pointer;color:var(--blue)}
details p{margin:6px 0;color:var(--muted)}.where{font-size:13px}
.verdict{display:flex;flex-wrap:wrap;gap:6px 16px;align-items:center}.verdict label{cursor:pointer}
.note{flex:1 1 240px;font:inherit;color:var(--text);background:var(--raised);border:1px solid var(--line);border-radius:8px;padding:6px 10px}
#out{display:none;margin-top:18px}#out textarea{width:100%;min-height:220px;font:13px/1.5 Consolas,monospace;color:var(--text);background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
</style></head><body><main>
<h1>Pawprint Testfragen</h1>
<p class="lead">__COUNT__ fertige Fragen zu deinen eigenen Gesprächen. Nichts davon verlässt diese Seite.</p>
<ol class="how">
<li>In einem Terminal <b>pawprint serve</b> starten und den Link öffnen.</li>
<li>Frage hier kopieren (Klick auf die Frage), im Browser einfügen und <b>Fragen</b> drücken.</li>
<li><b>Erwartung anzeigen</b>, mit Antwort und Quelle vergleichen, Urteil anklicken.</li>
<li>Am Ende <b>Ergebnis kopieren</b> und mir einfügen. Nur die schlechten Fälle sind darin ausgeschrieben.</li>
</ol>
<div class="bar"><span class="count" id="count"></span><button id="reset" type="button">Zurücksetzen</button><button id="copy" class="primary" type="button">Ergebnis kopieren</button></div>
__CARDS__
<div id="out"><p class="lead">Dieser Text ist kopiert. Falls nicht, markiere ihn selbst und kopiere ihn:</p><textarea id="text" readonly></textarea></div>
</main>
<script>
const cards=[...document.querySelectorAll('.card')];
const KEY='pawprint-testfragen-v1';
let saved={};try{saved=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
function persist(){const s={};cards.forEach(c=>{const n=c.dataset.n,v=c.querySelector('input[type=radio]:checked');s[n]={v:v?v.value:null,note:c.querySelector('.note').value}});try{localStorage.setItem(KEY,JSON.stringify(s))}catch(e){}}
function refresh(){const done=cards.filter(c=>c.querySelector('input[type=radio]:checked'));cards.forEach(c=>c.classList.toggle('done',!!c.querySelector('input[type=radio]:checked')));document.getElementById('count').textContent=done.length+' von '+cards.length+' bewertet'}
cards.forEach(c=>{const s=saved[c.dataset.n];if(s){if(s.v){const r=c.querySelector('input[value='+s.v+']');if(r)r.checked=true}c.querySelector('.note').value=s.note||''}
c.addEventListener('change',()=>{persist();refresh()});c.querySelector('.note').addEventListener('input',persist);
c.querySelector('.q').addEventListener('click',()=>{const t=c.dataset.q.replace(/\\s+\\(Filter:.*$|\\s+\\(Beliebige.*$/,'');try{navigator.clipboard.writeText(t)}catch(e){}});c.querySelector('.q').title='Klicken zum Kopieren';c.querySelector('.q').style.cursor='copy'});
document.getElementById('reset').addEventListener('click',()=>{if(!confirm('Alle Urteile löschen?'))return;cards.forEach(c=>{c.querySelectorAll('input[type=radio]').forEach(r=>r.checked=false);c.querySelector('.note').value=''});persist();refresh()});
document.getElementById('copy').addEventListener('click',()=>{
const L={gut:'passt',teils:'teils',falsch:'falsch',nichts:'nichts gefunden'},tally={gut:0,teils:0,falsch:0,nichts:0};const bad=[];let open=0;
cards.forEach(c=>{const v=c.querySelector('input[type=radio]:checked');if(!v){open++;return}tally[v.value]++;if(v.value!=='gut'){const n=c.querySelector('.note').value.trim();bad.push(c.dataset.n+'. ['+c.querySelector('.tag').textContent+'] '+c.dataset.q+'\\n   Urteil: '+L[v.value]+(n?'\\n   Notiz: '+n:''))}});
const t='Pawprint Testfragen: passt '+tally.gut+', teils '+tally.teils+', falsch '+tally.falsch+', nichts gefunden '+tally.nichts+', offen '+open+' (von '+cards.length+')\\n\\n'+(bad.length?bad.join('\\n\\n'):'Alles passt.');
document.getElementById('text').value=t;document.getElementById('out').style.display='block';try{navigator.clipboard.writeText(t)}catch(e){}});
refresh();
</script></body></html>"""

out = PAGE.replace("__COUNT__", str(len(entries))).replace("__CARDS__", "\n".join(CARDS))
target = HERE / "testfragen.html"
target.write_text(out, encoding="utf-8")
print(f"{len(picked)} questions from the history + {len(special)} special ones -> {target}")
by = {}
for e in picked:
    by[e["kind"]] = by.get(e["kind"], 0) + 1
print("by kind:", by, "| projects:", len(per_project))
