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

## Cost (CPU, first full index)

| Model | Index time | Peak RAM | Query |
|---|---|---|---|
| MiniLM-L12 multilingual (384 dim, 0.22 GB) | 64 s | low | 20-140 ms |
| multilingual-e5-large (1024 dim, 2.2 GB) | 2,074 s | ~7 GB | 57-260 ms |

A second index run only reads changed files and embeds new text: about 1 s.

## Decision

Default model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, hybrid mode.
Across all 40 questions hybrid MiniLM finds 37, hybrid e5-large 36, at a 30x lower indexing cost.
e5-large stays available with `PAWPRINT_MODEL=intfloat/multilingual-e5-large`.

Open points: 40 questions are too few to tune the fusion; on the hard set hybrid ranks below pure
vector search, so keyword weighting is worth revisiting once the set is larger. MiniLM only reads
the first 128 tokens of a chunk, which favours the user question at the start of each chunk.
