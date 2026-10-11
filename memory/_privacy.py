"""Single guarded import of Phase 1. Fails CLOSED: if privacy is missing,
everything is treated as sensitive and no cloud context is produced."""
from __future__ import annotations

try:
    from privacy.pipeline import sanitize
    from privacy.vault import Vault
    AVAILABLE = True
except Exception:  # any import problem -> fail closed
    sanitize = None  # type: ignore[assignment]
    Vault = None  # type: ignore[assignment]
    AVAILABLE = False


def looks_sensitive(text: str) -> int:
    """1 if Phase 1 would block / need permission / mask anything in `text`."""
    if not AVAILABLE:
        return 1
    try:
        g = sanitize(text)
        return 1 if (g.blocked or g.needs_permission or not g.vault.is_empty) else 0
    except Exception:
        return 1