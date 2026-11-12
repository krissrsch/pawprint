# Retrieval results

Measured on 2026-11-12 over the author's own transcripts: 240 files, 3,681 chunks, about 4 MB of text.
The questions themselves stay private (`eval/private/`, git-ignored) because they come from personal sessions.
A hit means the right session shows up among the first 5 distinct sessions returned.

## Golden set (30 questions, German, written after reading the target passage)

| Model | Mode | Recall@5 | MRR |
|---|---|---|---|
| MiniLM-L12 multilingual | keyword | 0.97 | 0.89 |
| MiniLM-L12 multilingual | vector | 0.77 | 0.69 |
| MiniLM-L12 multilingual | hybrid | 0.97 | 0.82 |
| multilingual-e5-large | vector | 1.00 | 0.94 |
| multilingual-e5-large | hybrid | 1.00 | 0.94 |

This set flatters keyword search: the questions share many words with the passages.

## Hard set (10 questions, English, paraphrased, about German passages)

| Model | Mode | Recall@5 | MRR |
|---|---|---|---|
| MiniLM-L12 multilingual | keyword | 0.60 | 0.48 |
| MiniLM-L12 multilingual | vector | 0.80 | 0.69 |
| MiniLM-L12 multilingual | hybrid | 0.80 | 0.54 |
| multilingual-e5-large | vector | 0.70 | 0.60 |
| multilingual-e5-large | hybrid | 0.60 | 0.49 |

## After the review fixes and a header on every chunk (2026-11-12, 3,856 chunks)

Every chunk now starts with a `[project | session title]` line, so later pieces of a long turn
keep their context. The line is stripped again for display and for the prompt sent to Claude.
Hybrid search with MiniLM, session-level recall@5 (MRR in brackets):

| Question set | Before | After |
|---|---|---|
| 30 German questions | 0.97 (0.83) | 0.97 (0.84) |
| 10 English paraphrased questions | 0.70 (0.53) | 0.80 (0.47) |

Recall improved on the hard set, MRR dropped a little. Ten questions cannot separate those two.

## `ask` end to end (11 questions, `eval/run_ask_eval.py`)

| | Result |
|---|---|
| Answerable (7) | 6 correct, all with citations, 1 wrongly refused |
| Unanswerable (4: cake recipe, capital of Australia, bank balance, a password) | 4 refused, none answered |

The wrongly refused question was vague ("the decrypted Pokémon file"); the passage that holds the
answer is a heap-offset dump that shares no words with it, and it sits outside the top 6. The same
question with the name in it ("Floink level 5") ranks it first. Claude's answer is not deterministic:
one borderline question (an excerpt that quotes a URL as part of a task, without a checked result)
flipped between refusing and answering on repeated runs, so it was dropped from the set.

## Big generated test set (798 questions, 2026-11-12)

`eval/build_testset.py` drew 400 chunks from 32 projects (no more than 35 per project, Pawprint's own
sessions left out) and had `claude -p` write two questions per chunk in four styles: paraphrase,
vague, the other language, and search-box keywords. Each question carries a verbatim evidence quote
from its chunk, checked by the script. `eval/run_big_eval.py` counts a hit when a retrieved chunk
contains that quote, so the set stays valid when chunking changes and duplicated passages count.

This set is much harder than the earlier ones and showed two real problems:

1. **Fusion.** With the usual RRF constant k=60, deep and weak vector ranks pushed good keyword hits
   out of the top 10: hybrid scored below keyword search alone (hit@10 0.56 vs 0.64).
2. **Truncation.** MiniLM reads about 128 tokens, so it saw roughly the first third of a 1,500-char
   chunk. Vector search found the answer in the top 10 for only 34 % of questions, and 31 % for
   pieces that are not the start of a turn.

Fixes, compared on the same questions (hybrid, hit@1 / hit@5 / hit@10 / MRR):

| Variant | hit@1 | hit@5 | hit@10 | MRR | session@5 |
|---|---|---|---|---|---|
| before: one vector per chunk, k=60 | 0.24 | 0.45 | 0.56 | 0.34 | 0.82 |
| k=10 | 0.29 | 0.59 | 0.69 | 0.42 | 0.88 |
| **450-char windows (best window counts) + k=10** | **0.35** | **0.66** | **0.75** | **0.49** | **0.89** |
| multilingual-e5-large, one vector per chunk, k=10 | 0.40 | 0.66 | 0.72 | 0.51 | 0.86 |

Vector search alone went from 0.34 to 0.53 hit@10 with windows, and from 0.38 to 0.57 on questions in
the other language. e5-large is stronger on same-language questions but weaker across languages
(0.33), ends up lower overall, and needs 35 minutes and 7 GB RAM to index, so windows with MiniLM
are the default. The first full index now takes about 3.5 minutes instead of one.

Hybrid hit@10 by question style after the fix: keywords 0.98, paraphrase 0.72, vague 0.77, other
language 0.53. Of the 199 remaining misses, 116 still return the right session in the top 5 (wrong
piece of the right conversation); 83 miss the session too, most of them cross-language (36).

The small sets did not get worse: 30 German questions 0.97 (MRR 0.84), 10 hard ones 0.80 (MRR 0.55).
`ask` on its 11 questions: 7 of 7 answerable correct with citations (the vague question that failed
before now works), 4 of 4 unanswerable refused.

## Query expansion, reranking, neighbours (2026-11-12)

Three ideas aimed at the 199 remaining misses, each measured before it went in.

**Reranker.** A cross-encoder reads question and passage together and reorders the hybrid top 20.
On 240 questions (60 per style), `jinaai/jina-reranker-v2-base-multilingual`: hit@1 0.33 -> 0.64,
hit@5 0.65 -> 0.78, MRR 0.47 -> 0.69, at 3.9 s per question on the CPU. `BAAI/bge-reranker-v2-m3-int8`
scored the same on 40 questions (MRR 0.68 vs 0.69) and was slower, so jina is the default.

**Query expansion.** `claude -p` rewrites the question into the other language and into 6-10
keywords; each of the three strings adds a keyword and a vector ranking to the fusion. On all 798
questions (rewrites made in batches of 40 by `eval/build_rewrites.py`):

| Variant | hit@1 | hit@5 | hit@10 | MRR | other language @10 |
|---|---|---|---|---|---|
| question only | 0.35 | 0.66 | 0.75 | 0.49 | 0.53 |
| + translation | 0.42 | 0.65 | 0.77 | 0.53 | 0.76 |
| + keywords | 0.46 | 0.76 | 0.84 | 0.59 | 0.75 |
| + translation + keywords | 0.46 | 0.77 | 0.85 | 0.59 | 0.86 |

**Which model rewrites the question?** The same 798 rewrites made by Sonnet and by Haiku, same retrieval:

| Rewrites by | hit@1 | hit@5 | hit@10 | MRR | other language @10 |
|---|---|---|---|---|---|
| none | 0.35 | 0.66 | 0.75 | 0.49 | 0.52 |
| Sonnet | 0.47 | 0.77 | 0.85 | 0.59 | 0.86 |
| Haiku, first prompt | 0.45 | 0.75 | 0.84 | 0.58 | 0.81 |
| **Haiku, prompt that forbids repeating the question's language** | 0.46 | 0.76 | 0.85 | 0.58 | 0.84 |

The first Haiku prompt sometimes returned an English question unchanged instead of translating it;
one extra sentence fixed that. A single call takes 2.4 s with Haiku and 4.0 s with Sonnet, and costs
about 0.02 instead of 0.32 US cents at API prices (the input is ~3,000 tokens either way, mostly
Claude Code's own system prompt). Haiku rewrites the question by default; the answer stays on Sonnet.

**Neighbouring chunks** for `ask` (send the pieces before and after each hit) were rejected: the
evidence was in the top 5 for 0.66 of questions and in top 5 plus neighbours for 0.70, with 2.5 times
the text. Sending the top 8 instead covers 0.72 with less text.

**Full pipeline** (`eval/run_pipeline_eval.py`, same 240 questions):

| | hit@1 | hit@5 | hit@10 | MRR |
|---|---|---|---|---|
| plain hybrid | 0.33 | 0.65 | 0.72 | 0.47 |
| + translation & keywords | 0.45 | 0.74 | 0.84 | 0.57 |
| + reranker | 0.72 | 0.88 | 0.89 | 0.79 |

hit@10 by style, plain -> pipeline: keywords 1.00 -> 1.00, paraphrase 0.68 -> 0.83, vague 0.73 -> 0.85,
other language 0.45 -> 0.88.

**On the 199 questions plain hybrid missed** (`eval/run_pipeline_eval.py failures`): the pipeline
puts 127 (0.64) into the top 10, 117 into the top 5 and 86 in first place. By style: keywords 1.00,
other language 0.77, vague 0.52, paraphrase 0.51. Of the 70 that are not even in the expanded
top 20, half still return the right session in the top 5; a sample shows some ambiguous questions
(another passage answers them too, for example a different installer build) and mostly very specific
details inside long passages.

`ask` end to end with the pipeline: 7 of 7 answerable correct with citations, 4 of 4 unanswerable
refused, 10-21 s per question. `ask` and the web answer button use the pipeline; plain search stays
instant and offers `--expand` and `--rerank`.

## Checklist of 35 questions, answered end to end (2026-11-12)

`eval/make_testfragen.py` picks 28 questions from the big set whose evidence occurs in exactly one chunk, from
sessions before the tool was built, plus 7 special ones (three that have no answer, two about a secret that
was typed into a chat, a project and date filter, the timing). `eval/run_testfragen.py` sends every question
through the real `ask` pipeline and lets Claude compare each answer with the source quote.

| Run | Graded "passt" by Claude | After reading the disputed ones |
|---|---|---|
| 1 | 31 of 35 | 34 of 35: three answers were right but quoted more than the grader's snippet |
| 2 | 34 of 35 | 35 of 35 |

The one answer graded wrong in both runs is the best one: the chat said "a new tunnel loses the ROM" and
corrected itself an hour later ("Ein neuer Tunnel löscht das ROM nicht"); Pawprint found both passages and
answered with the correction. The special questions passed in both runs: no answer invented for the three
unanswerable ones, the secret never printed, the filter kept to the project and dates, 10-21 s per question.
The user checked the first 5 by hand; all were right.

## Cost (CPU, first full index)

| Model | Index time | Peak RAM | Query |
|---|---|---|---|
| MiniLM-L12 multilingual (384 dim, 0.22 GB), windows | 200 s | low | ~10 ms (windows cached) |
| multilingual-e5-large (1024 dim, 2.2 GB) | 2,074 s | ~7 GB | 57-260 ms |

A second index run only reads changed files and embeds new text: a few seconds.

## Decision

Default model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, hybrid mode.
Across all 40 questions hybrid MiniLM finds 37, hybrid e5-large 36, at a 30x lower indexing cost.
e5-large stays available with `PAWPRINT_MODEL=intfloat/multilingual-e5-large`.

Open points: 40 questions are too few to tune the fusion; on the hard set hybrid ranks below pure
vector search, so keyword weighting is worth revisiting once the set is larger. MiniLM only reads
the first 128 tokens of a chunk, which favours the user question at the start of each chunk.

## recall for Claude sessions (S3, 2026-11-12)

Does the `recall` MCP tool help a Claude Code session? `eval/run_recall_eval.py` asks real questions from the
big set (paraphrased and vague ones, from four projects that still exist on disk) in a fresh `claude -p` session
(Sonnet, read-only tools Read/Grep/Glob, run in the project folder), once with the pawprint MCP server and once
without. A Haiku call compares each answer with the quote the question was made from; the answers were then
checked by hand, because the judge counted one "could not find it" as correct.

| 9 questions | correct (hand-checked) | avg time | avg tokens (incl. cache) | avg cost |
|---|---|---|---|---|
| without recall | 2 | 22 s | 36,000 | $0.05 |
| with recall | 4 | 33 s | 46,000 | $0.05 |

- The two extra answers are facts that only live in chats: why a line in a story file was rewritten, and where
  the user wanted an app to keep its data. Without recall the session searched the files and gave up.
- recall never made an answer worse. Where the files had the answer, both runs found it; with recall one of them
  took 2 instead of 4 turns.
- It did not save tokens on this set: the tool output and the extra turn cost about as much as the file reading
  it replaced. It costs about 11 s per question, mostly the reranker.
- 4 of 9 questions are unanswerable out of context ("the previous answer", "today"); both runs said so.
  The generated big set is a weak test for this; real recall tasks would be fairer.
- One answer noted that its excerpt was cut off at 600 characters.

Verdict: recall buys correctness on chat-only knowledge at the same cost, not token savings.
