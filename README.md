# Pawprint

Ask your own Claude Code history.

Pawprint indexes the session transcripts in `~/.claude/projects/` and lets you
search them and ask questions in plain language. Search and embeddings run
locally; answers cite the sessions they come from.

Status: early work in progress. Indexing, hybrid search, `ask` and a local web UI work.

```
pawprint index
pawprint search "how did I fix the login redirect"
pawprint ask "how did I fix the login redirect"
pawprint serve        # local web UI, prints a link with a one-time token
```

`ask` needs a logged-in `claude` CLI. It sends only the best few excerpts, redacted
again, and the answer cites them as `[Quelle n]` or says it found nothing.

## Privacy

Transcripts never leave your machine except for the few passages sent to
`claude -p` when you run `pawprint ask`. Secrets are redacted before indexing
and again before sending. This repository contains only invented test
transcripts.

## Development

```
python -m venv .venv
.venv/Scripts/pip install -e .[dev]
.venv/Scripts/pytest
```

License: MIT

## Web UI

`pawprint serve` listens on 127.0.0.1 only. The printed link carries a random token after
the `#`, so it never reaches the server or any log; requests without it get 401, and
requests with a foreign `Host` header are refused (DNS rebinding). The page offers search,
questions, filters by project and date, and answers whose `[Quelle n]` markers jump to the
excerpt they cite.
