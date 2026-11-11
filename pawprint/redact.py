"""Mask secrets before text is indexed or sent anywhere."""
from __future__ import annotations

import re

MASK = "[REDACTED]"

# (pattern, replacement). Order matters: specific token shapes first.
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), MASK),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{10,}"), MASK),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"), MASK),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"), MASK),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}"), MASK),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), MASK),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"), MASK),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), MASK),
    (re.compile(r"\bnfp_[A-Za-z0-9]{20,}"), MASK),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), MASK),  # JWT
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{20,}"), r"\1" + MASK),
    # user:password@host in URLs
    (re.compile(r"(?i)(\b[a-z][a-z0-9+.\-]*://[^/\s:@]+:)[^@\s/]+(@)"), r"\1" + MASK + r"\2"),
    # KEY=value / "key": "value" for secret-looking names
    (
        re.compile(
            r"(?i)\b([A-Za-z0-9_\-]*(?:password|passwd|passwort|secret|token|api[_\-]?key|apikey|private[_\-]?key)"
            r"[A-Za-z0-9_\-]*[\"']?\s*[:=]\s*[\"']?)([^\s\"',;]{6,})"
        ),
        r"\1" + MASK,
    ),
]


def redact(text: str) -> str:
    for pat, rep in _RULES:
        text = pat.sub(rep, text)
    return text
