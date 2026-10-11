# RAVEN Privacy Core - Failsafe
# Final safety net on already-masked text

import re
from typing import Dict, Optional
from .config import DEFAULT_THRESHOLDS
from .normalize import normalize_for_detection

# 6+ digits, allowing single space/hyphen between digits ("9876 543 210")
_DIGIT_RUN = re.compile(r'\d(?:[\s\-]?\d)+')

# Harmless only if the run ITSELF is money (currency right before/after it)
_MONEY_BEFORE = re.compile(r'(?:₹|\brs\.?|\binr|\$)\s*$', re.IGNORECASE)
_MONEY_AFTER = re.compile(r'^\s*(?:rupees?|rupaye|rs\b|रुपये|रुपए|inr)', re.IGNORECASE)

_KEYWORDS = (
    r'password|passcode|pin|otp|cvv|code|secret|token|api\s*key|private\s*key|'
    r'पासवर्ड|पिन|ओटीपी|कोड|सीक्रेट'
)
# keyword, optional ":" "=" "is" "hai", then a value that has a digit and is not a [PLACEHOLDER]
_SECRET_AFTER = re.compile(
    r'(?<!\w)(?:' + _KEYWORDS + r')\s*(?::|=|\bis\b|\bhai\b|है)?\s*(?!\[)(?=\S*\d)\S+',
    re.IGNORECASE | re.UNICODE,
)
# "1234 otp"
_SECRET_BEFORE = re.compile(
    r'(?<!\d)\d{4,8}\s*(?:code|otp|pin|cvv|ओटीपी)(?!\w)',
    re.IGNORECASE | re.UNICODE,
)


def _is_money(text: str, start: int, end: int) -> bool:
    return bool(_MONEY_BEFORE.search(text[max(0, start - 6):start])
                or _MONEY_AFTER.match(text[end:end + 12]))


def check_digit_runs(text: str, min_length: int = 6) -> bool:
    """True if an unmasked ID-like digit run remains."""
    for m in _DIGIT_RUN.finditer(text):
        digits = re.sub(r'\D', '', m.group())
        if len(digits) >= min_length and not _is_money(text, m.start(), m.end()):
            return True
    return False


def check_secret_patterns(text: str) -> bool:
    return bool(_SECRET_AFTER.search(text) or _SECRET_BEFORE.search(text))


def failsafe(text: str, config: Optional[Dict] = None) -> Dict:
    """
    Final check on masked text.
    Returns {"blocked": bool, "reason": str | None}
    """
    if not text:
        return {"blocked": False, "reason": None}

    config = config or {}
    thresholds = config.get("thresholds", DEFAULT_THRESHOLDS)
    min_run = thresholds.get("digit_run_length", 6)
    if not config.get("policy", {}).get("block_on_failsafe", True):
        return {"blocked": False, "reason": None}

    # Devanagari digits -> ASCII (same length, offsets safe)
    t = normalize_for_detection(text)

    if check_digit_runs(t, min_run):
        return {"blocked": True, "reason": "failsafe:digits"}
    if check_secret_patterns(t):
        return {"blocked": True, "reason": "failsafe:secret"}
    return {"blocked": False, "reason": None}