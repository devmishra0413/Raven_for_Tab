# RAVEN Privacy Core - Normalize
# Whisper output ke liye: Devanagari digits + spoken digits -> ASCII digits

import re

# Length-preserving (1 char -> 1 char), isliye offsets safe rehte hain
_DEVANAGARI = str.maketrans("०१२३४५६७८९", "0123456789")

_SPOKEN = {
    # English
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    # Hinglish
    "shunya": "0", "ek": "1", "do": "2", "teen": "3", "char": "4", "chaar": "4",
    "panch": "5", "paanch": "5", "chhe": "6", "chhah": "6", "che": "6",
    "saat": "7", "sat": "7", "aath": "8", "ath": "8", "nau": "9",
    # Devanagari
    "शून्य": "0", "एक": "1", "दो": "2", "तीन": "3", "चार": "4",
    "पांच": "5", "पाँच": "5", "छह": "6", "छः": "6", "छे": "6",
    "सात": "7", "आठ": "8", "नौ": "9",
}

_SEP = r'[\s,.\-]'
_WORD = '(?:' + '|'.join(
    re.escape(w) for w in sorted(_SPOKEN, key=len, reverse=True)
) + ')(?!' + r'[^\s,.\-]' + ')'

# 4+ digit-words in a row ("nau aath saat chhe ..."). Single "one"/"do"/"ek" safe rehte hain.
_SPOKEN_RUN = re.compile(
    r'(?<![^\s,.\-])' + _WORD + '(?:' + _SEP + r'+' + _WORD + r'){3,}',
    re.IGNORECASE | re.UNICODE,
)
_TOKEN = re.compile(r'[^\s,.\-]+')


def normalize_for_detection(text: str) -> str:
    """Devanagari digits -> ASCII. Same length, so indices stay valid."""
    return text.translate(_DEVANAGARI) if text else text


def normalize_spoken_digits(text: str) -> str:
    """
    'nau aath saat chhe paanch' -> '98765'
    Length badal jati hai, isliye pipeline me sabse pehle, ek baar chalao.
    """
    if not text:
        return text

    def repl(m: re.Match) -> str:
        return ''.join(_SPOKEN[t.lower()] for t in _TOKEN.findall(m.group(0)))

    return _SPOKEN_RUN.sub(repl, text)