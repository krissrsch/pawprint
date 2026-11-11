# Pawprint

Ask your own Claude Code history.

Pawprint indexes the session transcripts in `~/.claude/projects/` and lets you
search them and ask questions in plain language. Search and embeddings run
locally; answers cite the sessions they come from.

Status: early work in progress (parsing, redaction and chunking so far).

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
