"""RAVEN Memory - text utilities (stdlib only).

normalize_content(): NFC, strip invisible/control chars, Devanagari digits,
casefold, collapse whitespace. Used for search index + dedupe hash.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_INVISIBLE = re.compile(
    "[\u200B\u200C\u200D\uFEFF\u00AD\u2060\u2061\u2062\u2063\u2064"
    "\u034F\u180E\u061C\u115F\u1160\u17B4\u17B5]"
)
_CONTROL = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]")
_MULTI_WS = re.compile(r"\s+")

# Devanagari combining marks (signs, matras, virama, nukta, vedic/vocalic).
# unicode61 does NOT treat these as token chars, so words get split.
DEVANAGARI_MARKS = "".join(
    chr(c)
    for c in (
        list(range(0x0900, 0x0904))
        + list(range(0x093A, 0x0950))
        + list(range(0x0951, 0x0958))
        + [0x0962, 0x0963]
    )
)

# A search token = letters/digits (any script) + Devanagari marks. '_' excluded
# on purpose (the FTS tokenizer treats it as a separator).
_TOKEN = re.compile(r"(?:[^\W_]|[\u0900-\u0903\u093a-\u094f\u0951-\u0957\u0962\u0963])+")
MAX_QUERY_TOKENS = 16
MAX_TOKEN_LEN = 64


def clean_content(text: str) -> str:
    """Text as stored: NFC, invisible + control chars removed, stripped."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = _INVISIBLE.sub("", text)
    text = _CONTROL.sub("", text)
    return text.strip()


def normalize_content(text: str) -> str:
    """Normalized form used for indexing and dedupe."""
    text = clean_content(text)
    if not text:
        return ""
    text = text.translate(_DEVANAGARI_DIGITS).casefold()
    return _MULTI_WS.sub(" ", text).strip()


def content_hash(text: str) -> str:
    """SHA-256 of the normalized text."""
    return hashlib.sha256(normalize_content(text).encode("utf-8")).hexdigest()


def query_tokens(query: str) -> list[str]:
    """Free text -> safe word tokens (no operators, quotes, punctuation)."""
    toks = _TOKEN.findall(normalize_content(query))
    return [t[:MAX_TOKEN_LEN] for t in toks[:MAX_QUERY_TOKENS]]


def sanitize_fts_query(query: str) -> str:
    """Free text -> safe FTS5 MATCH string, e.g. '"rah"* OR "ka"'.

    Tokens only contain letters/digits/marks, so nothing user-typed can act as
    an FTS operator. Tokens of 3+ chars become prefix queries (helps Hindi
    inflection: किताब -> किताबें). Returns "" if nothing searchable.
    """
    parts = [f'"{t}"*' if len(t) >= 3 else f'"{t}"' for t in query_tokens(query)]
    return " OR ".join(parts)


def sanitize_like_tokens(query: str) -> list[str]:
    """Free text -> LIKE patterns (%tok%). Tokens never contain % or _."""
    return [f"%{t}%" for t in query_tokens(query) if len(t) >= 2]