# RAVEN Privacy Core - Vault
# In-memory raw <-> placeholder mapping. Never persisted.

import re
from typing import Iterator


class Vault:
    """Same (kind, raw value) always gets the same placeholder within one request."""

    _PH = re.compile(r'\[\s*([A-Za-z]+_\d+)\s*\]')

    def __init__(self):
        self._by_key: dict[tuple[str, str], str] = {}   # (KIND, normalized raw) -> placeholder
        self._by_ph: dict[str, str] = {}                # placeholder -> original raw
        self._counters: dict[str, int] = {}

    def mask(self, kind: str, raw: str) -> str:
        if not raw:
            return ""
        kind = kind.upper()
        key = (kind, " ".join(raw.lower().split()))
        ph = self._by_key.get(key)
        if ph:
            return ph
        n = self._counters.get(kind, 0) + 1
        self._counters[kind] = n
        ph = f"[{kind}_{n}]"
        self._by_key[key] = ph
        self._by_ph[ph] = raw.strip()      # original casing kept for unmask
        return ph

    def unmask(self, text: str) -> str:
        """
        Restore originals. Accepts [PHONE_1], [phone_1], [ PHONE_1 ].
        Surrounding spaces and markdown (**[PHONE_1]**) are left untouched.
        Unknown placeholders stay as-is.
        """
        if not text or not self._by_ph:
            return text

        def repl(m: re.Match) -> str:
            return self._by_ph.get(f"[{m.group(1).upper()}]", m.group(0))

        return self._PH.sub(repl, text)

    def clear(self) -> None:
        self._by_key.clear()
        self._by_ph.clear()
        self._counters.clear()

    def get_findings(self) -> list[dict]:
        """Type + placeholder only, never raw values."""
        out = []
        for ph in self._by_ph:
            m = re.match(r'\[([A-Z]+)_\d+\]', ph)
            if m:
                out.append({"type": m.group(1).lower(), "placeholder": ph})
        return out

    def items(self) -> Iterator[tuple[str, str]]:
        """(raw, placeholder) pairs."""
        return ((raw, ph) for ph, raw in self._by_ph.items())

    @property
    def is_empty(self) -> bool:
        return not self._by_ph

    def __repr__(self) -> str:
        return f"Vault({len(self._by_ph)} items)"

    __str__ = __repr__