"""S3 of docs/plan-zweites-gehirn.md: does `recall` save tokens and time?

Runs real recognition questions twice with `claude -p`, once with the pawprint MCP tool and once without it, in the
project's own folder, with read-only tools. A judge call (Haiku) compares each answer with the quote the question was
generated from. Prints cost, tokens, time, turns and correctness per variant.

Questions come from eval/private/big_set.json (private, git-ignored); results go to eval/private/recall_results.json.
Every run is a full Claude session, so keep the set small: 10 questions = 20 sessions + 20 judge calls.

    python eval/run_recall_eval.py [--n 10] [--only with|without]
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "eval" / "private"
# project name in the index -> folder where that project lives now (chats of moved or deleted projects cannot be a fair baseline)
FOLDERS = {
    "Pokemon Rumble EX": "C:/Programmieren/Apps/Pokemon Rumble EX",
    "Zugtool-Plan": "C:/Programmieren/Websites/Zugtool-Plan",
    "PhilaWelser": "C:/Programmieren/Websites/PhilaWelser",
    "AgentOS": "C:/Programmieren/Tools/AgentOS",
}
PROMPT = "{q}\n\nAntworte knapp auf Deutsch (höchstens 3 Sätze). Wenn du es nicht herausfinden kannst, sag das."
TOOLS = "Read,Grep,Glob"


def pick(n: int) -> list[dict]:
    items = [x for x in json.load(open(PRIVATE / "big_set.json", encoding="utf-8"))
             if x["project"] in FOLDERS and x["style"] in ("paraphrase", "vague") and Path(FOLDERS[x["project"]]).is_dir()]
    random.Random(7).shuffle(items)
    out, per = [], {}
    for x in items:  # spread over the projects
        if per.get(x["project"], 0) < max(1, n // 3):
            per[x["project"]] = per.get(x["project"], 0) + 1
            out.append(x)
    return out[:n]


def claude(args: list[str], prompt: str, cwd: str | None, timeout: int = 600) -> dict:
    # the prompt goes through stdin: --tools and --mcp-config take several values and would swallow a positional prompt
    p = subprocess.run(["claude", "-p", "--output-format", "json", "--no-session-persistence", *args], input=prompt,
                       capture_output=True, cwd=cwd, timeout=timeout, encoding="utf-8", errors="replace")
    try:
        return json.loads(p.stdout)
    except ValueError:
        return {"result": "", "is_error": True, "stderr": p.stderr[-300:]}


def run(task: dict, with_recall: bool, empty_mcp: str) -> dict:
    args = ["--model", "sonnet", "--tools", TOOLS, "--max-budget-usd", "1.5"]
    args += ["--allowedTools", "mcp__pawprint__recall"] if with_recall else ["--strict-mcp-config", "--mcp-config", empty_mcp]
    r = claude(args, PROMPT.format(q=task["q"]), FOLDERS[task["project"]])
    u = r.get("usage") or {}
    return {"answer": r.get("result", ""), "error": bool(r.get("is_error")), "cost": r.get("total_cost_usd", 0.0),
            "ms": r.get("duration_ms", 0), "turns": r.get("num_turns", 0),
            "tokens": sum(u.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
            "denied": [d.get("tool_name") for d in r.get("permission_denials", [])]}


def judge(task: dict, answer: str) -> bool:
    q = (f"Frage: {task['q']}\nBelegstelle aus dem Originalchat: {task['evidence']}\nAntwort: {answer}\n\n"
         "Stimmt die Antwort inhaltlich mit der Belegstelle überein (die entscheidende Tatsache ist genannt und nicht widersprochen)? "
         "Antworte nur mit JA oder NEIN.")
    return claude(["--model", "haiku", "--tools", ""], q, None).get("result", "").strip().upper().startswith("JA")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--only", choices=("with", "without"))
    a = ap.parse_args()
    out_file = PRIVATE / "recall_results.json"
    results = json.load(open(out_file, encoding="utf-8")) if out_file.exists() else {}
    with tempfile.TemporaryDirectory() as d:
        empty = str(Path(d) / "empty.json")
        Path(empty).write_text('{"mcpServers":{}}')
        for i, t in enumerate(pick(a.n)):
            for variant in ("without", "with"):
                key = f"{t['hash']}:{t['style']}:{variant}"  # two questions can come from the same passage
                if (a.only and a.only != variant) or key in results:
                    continue
                r = run(t, variant == "with", empty)
                r["correct"] = judge(t, r["answer"]) if r["answer"] else False
                r["project"], r["q"] = t["project"], t["q"]
                results[key] = r
                json.dump(results, open(out_file, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                print(f"{i + 1:2} {variant:7} {r['ms'] / 1000:5.0f}s {r['turns']:2} turns {r['tokens']:8} tok ${r['cost']:.2f} "
                      f"{'OK ' if r['correct'] else 'NO '} {t['project']}", flush=True)
    for variant in ("without", "with"):
        rs = [v for k, v in results.items() if k.endswith(":" + variant)]
        if rs:
            n = len(rs)
            print(f"{variant:8} n={n} correct={sum(r['correct'] for r in rs)} avg {sum(r['ms'] for r in rs) / n / 1000:.0f}s "
                  f"{sum(r['tokens'] for r in rs) // n} tok ${sum(r['cost'] for r in rs) / n:.2f} {sum(r['turns'] for r in rs) / n:.1f} turns")


if __name__ == "__main__":
    sys.exit(main())
