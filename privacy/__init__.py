# RAVEN Privacy Core - Phase 1
# Exports the public API

from .normalize import normalize_for_detection, normalize_spoken_digits
from .entity_filter import entity_filter
from .topic_guard import topic_guard
from .failsafe import failsafe
from .vault import Vault
from .config import DEFAULT_CONFIG, merge_config
from .pipeline import sanitize, GuardResult

__all__ = [
    "sanitize",
    "GuardResult",
    "Vault",
    "normalize_for_detection",
    "normalize_spoken_digits",
    "regex_filter",
    "PATTERNS",
    "entity_filter",
    "topic_guard",
    "failsafe",
    "DEFAULT_CONFIG",
    "merge_config",
]