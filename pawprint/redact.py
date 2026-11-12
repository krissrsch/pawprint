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
    (re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}"), MASK),  # Stripe
    (re.compile(r"\bnpm_[A-Za-z0-9]{30,}"), MASK),
    (re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}"), MASK),  # GitLab
    (re.compile(r"\bhf_[A-Za-z0-9]{30,}"), MASK),  # Hugging Face
    (re.compile(r"\bsbp_[A-Za-z0-9]{30,}"), MASK),  # Supabase
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), MASK),  # JWT
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{20,}"), r"\1" + MASK),
    # user:password@host in URLs; greedy up to the last "@", so a raw "@" or "/" in the password is covered too
    # (masking a bit of host or path in odd URLs is the safe side)
    (re.compile(r"(?i)(\b[a-z][a-z0-9+.\-]*://[^/\s:@]+:)\S+(@)"), r"\1" + MASK + r"\2"),
]

# KEY=value / "key": "value" for secret-looking names. Handled apart from the list above because the value
# must be checked: plain words after "tokens:" or "secret_x:" are ordinary text, not secrets.
_KV = re.compile(
    r"(?i)\b([A-Za-z0-9_\-]*(?:password|passwd|passwort|pwd|secret|token|api[_\-]?key|apikey|private[_\-]?key)"
    r"[A-Za-z0-9_\-]*[\"']?\s*[:=]\s*[\"']?)([^\s\"',;]{6,})"
)
_PASSWORD_NAME = re.compile(r"(?i)pass|pwd")


def _looks_like_key(v: str) -> bool:
    v = v.strip("`.)(]}>")
    has_digit = any(c.isdigit() for c in v)
    has_letter = any(c.isalpha() for c in v)
    mixed_case = any(c.islower() for c in v) and any(c.isupper() for c in v)
    return (len(v) >= 8 and has_digit and has_letter) or (len(v) >= 20 and mixed_case)


def _kv(m: re.Match) -> str:
    # names with "pass" are masked whatever the value is; for token/secret/api key only values shaped like a key
    return m.group(1) + MASK if _PASSWORD_NAME.search(m.group(1)) or _looks_like_key(m.group(2)) else m.group(0)


def redact(text: str) -> str:
    for pat, rep in _RULES:
        text = pat.sub(rep, text)
    return _KV.sub(_kv, text)
