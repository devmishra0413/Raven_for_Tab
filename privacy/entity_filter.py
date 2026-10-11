# RAVEN Privacy Core - Entity Filter
# Mask user-supplied entities (names, places) from text

import re
import unicodedata
from typing import List, Tuple, Optional
from .vault import Vault


def _is_word_char(ch: str) -> bool:
    # Letters, Marks (matras/virama), Numbers, underscore.
    # Python's \w misses Devanagari matras, so check the category.
    return ch == "_" or unicodedata.category(ch)[0] in "LMN"


def _parse_entities(entities: List) -> List[Tuple[str, str]]:
    """Flatten to (alias, KIND) pairs."""
    pairs = []
    for ent in entities:
        if isinstance(ent, str):
            name, kind, aliases = ent, "PERSON", [ent]
        elif isinstance(ent, dict):
            name = ent.get("name", "")
            kind = ent.get("type", "person")
            aliases = list(ent.get("aliases") or [])
            if name:
                aliases.append(name)
        else:
            continue
        kind = re.sub(r"[^A-Z]", "", str(kind).upper()) or "PERSON"
        for a in aliases:
            a = (a or "").strip()
            if len(a) >= 2:
                pairs.append((a, kind))
    return pairs


def find_entity_matches(
    text: str,
    entities: List,
    vault: Vault,
    min_len: int = 2,
) -> List[Tuple[int, int, str, str]]:
    """Return non-overlapping (start, end, kind, placeholder), sorted by start."""
    if not text or not entities:
        return []

    # Longest alias first so "Ravi Kumar" wins over "Ravi"
    pairs = sorted(set(_parse_entities(entities)), key=lambda p: -len(p[0]))

    candidates = []  # (start, end, kind, alias)
    for alias, kind in pairs:
        if len(alias) < min_len:
            continue
        for m in re.finditer(re.escape(alias), text, re.IGNORECASE):
            s, e = m.span()
            if s > 0 and _is_word_char(text[s - 1]):
                continue
            if e < len(text) and _is_word_char(text[e]):
                continue
            candidates.append((s, e, kind, alias))

    # Longer first, then earlier; drop overlaps
    candidates.sort(key=lambda c: (-(c[1] - c[0]), c[0]))
    kept = []
    for s, e, kind, alias in candidates:
        if any(s < ke and e > ks for ks, ke, _, _ in kept):
            continue
        kept.append((s, e, kind, alias))

    # Mask only the survivors (no stray placeholders in vault)
    kept.sort(key=lambda c: c[0])
    return [(s, e, kind, vault.mask(kind, text[s:e])) for s, e, kind, _ in kept]


def entity_filter(
    text: str,
    entities: Optional[List] = None,
    vault: Optional[Vault] = None,
    fuzzy_enabled: bool = False,   # kept for pipeline compatibility, unused
    fuzzy_distance: int = 1,       # kept for pipeline compatibility, unused
) -> Tuple[str, List[dict]]:
    """Mask entities. Returns (masked_text, findings)."""
    if not text or not entities:
        return text, []
    if vault is None:
        vault = Vault()

    matches = find_entity_matches(text, entities, vault)
    if not matches:
        return text, []

    out = text
    for s, e, _, ph in reversed(matches):
        out = out[:s] + ph + out[e:]

    findings = [{"type": k.lower(), "placeholder": ph} for _, _, k, ph in matches]
    return out, findings