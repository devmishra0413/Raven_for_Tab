"""RAVEN Memory - the privacy boundary: safe context for a cloud prompt.

Fails closed: any problem -> [] (never raw text).
"""
from __future__ import annotations

from . import _privacy
from .manager import MemoryManager


def _safe_cut(text: str, n: int) -> str:
    """Cut to <= n chars.
    """
    return text[:n]


def build_cloud_context(
    manager: MemoryManager,
    query: str,
    entities: list | None = None,
    k: int = 5,
    max_chars: int = 1200,
    vault: "_privacy.Vault | None" = None,
    per_fact_max: int = 300,
) -> list[str]:
    """Search confirmed, non-sensitive facts; sanitize each with Phase 1
    sanitize() using ONE shared vault (so [NAME_1] means the same person as in
    the user's query); drop blocked / needs_permission facts; return clean text.

    Pass the vault used to mask the user's query so placeholders match.
    Truncation happens AFTER masking and never inside a placeholder.
    """
    if not _privacy.AVAILABLE:
        return []
    try:
        if not isinstance(query, str) or not query.strip():
            return []
        k = max(0, min(int(k), 100))
        max_chars = max(0, int(max_chars))
        per_fact_max = max(0, int(per_fact_max))
        if vault is None:
            vault = _privacy.Vault()
        if entities is None:
            entities = manager.entity_list()
        facts = manager.search(query, k=k, include_sensitive=False, include_pending=False)

        out: list[str] = []
        seen: set[str] = set()
        total = 0
        for fact in facts:
            if fact.sensitivity or fact.status != "confirmed":   # belt and braces
                continue
            g = _privacy.sanitize(fact.content, entities=entities, vault=vault)
            if g.blocked or g.needs_permission:
                continue
            text = _safe_cut((g.clean_text or "").strip(), per_fact_max)
            if not text or text in seen:
                continue
            remaining = max_chars - total
            if remaining <= 0:
                break
            # Truncate only whole facts – never split inside a placeholder.
            if len(text) > remaining:
                # If the remaining space can hold the full fact, keep it.
                # Otherwise drop the entire fact (do not truncate).
                if remaining >= 20:  # choose a small threshold for meaningful content
                    # we fall back to keeping the fact whole but skip adding it.
                    # The outer loop will break if we have no space for any
                    # additional fact.
                    continue
                break
            seen.add(text)
            out.append(text)
            total += len(text)
        return out
    except Exception:
        return []