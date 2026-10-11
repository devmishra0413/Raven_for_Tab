# RAVEN Privacy Core - Regex Filter
# Pattern-based detection and masking of sensitive data

import re
from typing import List, Tuple
from .vault import Vault
from .normalize import normalize_for_detection


# ---------- checksums ----------
def luhn_check(num: str) -> bool:
    digits = [int(c) for c in num if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_D = [
    [0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],
    [3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],
    [6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],
    [9,8,7,6,5,4,3,2,1,0],
]
_P = [
    [0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],
    [8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],
    [2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8],
]


def verhoeff_check(number: str) -> bool:
    if not (number.isdigit() and len(number) == 12):
        return False
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def _digits(v: str) -> str:
    return re.sub(r'\D', '', v)


def _valid_ip(v: str) -> bool:
    return all(int(p) <= 255 for p in v.split('.'))


# ---------- patterns ----------
# validator: value passes -> mask directly.
# context: if validator fails (or missing validator + require_context), mask only when
#          a context word is near. No validator and no require_context -> always mask.
PATTERNS = [
    {"kind": "AADHAAR", "priority": 100,
     "pattern": r'(?<!\d)([2-9]\d{3}[ \-]?\d{4}[ \-]?\d{4})(?!\d)',
     "validator": lambda v: verhoeff_check(_digits(v)),
     "context": ['aadhaar', 'aadhar', 'adhar', 'uid', 'आधार']},
    {"kind": "PAN", "priority": 100,
     "pattern": r'(?<![A-Za-z0-9])([A-Za-z]{5}\d{4}[A-Za-z])(?![A-Za-z0-9])'},
    {"kind": "CARD", "priority": 95,
     "pattern": r'(?<!\d)(\d{4}(?:[ \-]?\d{4}){2,3}(?:[ \-]?\d{1,3})?)(?!\d)',
     "validator": lambda v: luhn_check(_digits(v)),
     "context": ['card', 'debit', 'credit', 'कार्ड']},
    {"kind": "EMAIL", "priority": 90,
     "pattern": r'(?<![\w.%+\-])([A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,})(?![\w@])'},
    {"kind": "UPI", "priority": 85,
     "pattern": r'(?<![\w.%+\-])([A-Za-z0-9._\-]{2,}@[A-Za-z]{2,})(?![\w@]|\.\w)'},
    {"kind": "IFSC", "priority": 80,
     "pattern": r'(?<![A-Za-z0-9])([A-Za-z]{4}0[A-Za-z0-9]{6})(?![A-Za-z0-9])'},
    {"kind": "PHONE", "priority": 75,
     "pattern": r'(?<![\d+])((?:\+?91[ \-]?|0)?[6-9]\d{4}[ \-]?\d{5})(?!\d)'},
    {"kind": "PASSPORT", "priority": 70,
     "pattern": r'(?<![A-Za-z0-9])([A-Za-z]\d{7})(?![A-Za-z0-9])',
     "require_context": True, "context": ['passport', 'पासपोर्ट']},
    {"kind": "VEHICLE", "priority": 65,
     "pattern": r'(?<![A-Za-z0-9])([A-Za-z]{2}[ \-]?\d{1,2}[ \-]?[A-Za-z]{1,3}[ \-]?\d{4})(?![A-Za-z0-9])'},
    {"kind": "OTP", "priority": 60,
     "pattern": r'(?<!\d)(\d{4,8})(?!\d)',
     "require_context": True,
     "context": ['otp', 'verification', 'verify', 'code', 'ओटीपी', 'कोड']},
    {"kind": "PIN", "priority": 62,
     "pattern": r'(?<!\d)(\d{4,6})(?!\d)',
     "require_context": True,
     "context": ['pin', 'pincode', 'postal', 'पिन', 'पिनकोड']},
    {"kind": "ACCOUNT", "priority": 50,
     "pattern": r'(?<!\d)(\d{9,18})(?!\d)',
     "require_context": True,
     "context": ['account', 'a/c', 'acct', 'खाता', 'अकाउंट']},
    {"kind": "IP", "priority": 45,
     "pattern": r'(?<![\d.])((?:\d{1,3}\.){3}\d{1,3})(?![\d.])',
     "validator": _valid_ip, "require_context": False},
]

# compile once
for _p in PATTERNS:
    _p["_re"] = re.compile(_p["pattern"], re.UNICODE)
    ctx = _p.get("context")
    _p["_ctx"] = re.compile(
        r'(?<!\w)(?:' + '|'.join(re.escape(w) for w in ctx) + r')(?!\w)',
        re.IGNORECASE | re.UNICODE) if ctx else None

CTX_BEFORE, CTX_AFTER = 40, 15


def _context_near(p: dict, text: str, s: int, e: int) -> bool:
    if not p["_ctx"]:
        return False
    return bool(p["_ctx"].search(text[max(0, s - CTX_BEFORE):s])
                or p["_ctx"].search(text[e:e + CTX_AFTER]))


def find_matches(text: str, vault: Vault) -> List[Tuple[int, int, str, str]]:
    """Return non-overlapping (start, end, kind, placeholder), sorted by start."""
    cands = []  # (start, end, kind, priority, raw)
    for p in PATTERNS:
        validator = p.get("validator")
        for m in p["_re"].finditer(text):
            s, e = m.span(1)
            raw = m.group(1)
            ok = bool(validator(raw)) if validator else None

            if ok:
                accept = True
            elif p.get("require_context", validator is not None):
                # validator failed, or pattern is too generic: need context
                accept = _context_near(p, text, s, e)
            else:
                accept = True  # specific pattern, no context needed

            if accept:
                cands.append((s, e, p["kind"], p["priority"], raw))

    cands.sort(key=lambda c: (-c[3], -(c[1] - c[0]), c[0]))
    kept = []
    for s, e, kind, _, raw in cands:
        if any(s < ke and e > ks for ks, ke, _, _ in kept):
            continue
        kept.append((s, e, kind, raw))

    # Placeholders only for survivors, numbered in text order
    kept.sort(key=lambda c: c[0])
    return [(s, e, kind, vault.mask(kind, raw)) for s, e, kind, raw in kept]


def regex_filter(text: str, vault: Vault) -> Tuple[str, List[dict]]:
    """Mask sensitive patterns. Returns (masked_text, findings)."""
    if not text:
        return text, []

    # length-preserving (Devanagari digits -> ASCII), so indices map to original
    work = normalize_for_detection(text)
    matches = find_matches(work, vault)
    if not matches:
        return text, []

    out = text
    for s, e, _, ph in reversed(matches):
        out = out[:s] + ph + out[e:]

    findings = [{"type": k.lower(), "placeholder": ph} for _, _, k, ph in matches]
    return out, findings