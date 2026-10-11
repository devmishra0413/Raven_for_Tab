# RAVEN Privacy Core - Topic Guard
# Detect sensitive topics before anything goes to the cloud

import re
from functools import lru_cache
from typing import Dict, Optional, Tuple
from .config import DEFAULT_SENSITIVE_TOPICS


@lru_cache(maxsize=256)
def _compile(keywords: Tuple[str, ...]) -> Optional[re.Pattern]:
    """One combined regex per keyword set (cached)."""
    ascii_kw, other_kw = [], []
    for kw in keywords:
        kw = (kw or "").strip()
        if not kw:
            continue
        (ascii_kw if kw.isascii() else other_kw).append(re.escape(kw))
    parts = []
    if ascii_kw:
        # whole word for Latin text: "case" must not hit "showcase"
        parts.append(r'(?<![A-Za-z0-9_])(?:' + '|'.join(ascii_kw) + r')(?![A-Za-z0-9_])')
    if other_kw:
        # Devanagari: plain substring, because Hindi adds suffixes (लोन -> लोनों)
        # and Python's \w ignores matras, so \b-style checks are unreliable
        parts.append('(?:' + '|'.join(other_kw) + ')')
    if not parts:
        return None
    return re.compile('|'.join(parts), re.IGNORECASE)


def check_topic(text: str, topic_name: str, topic_config: Dict) -> bool:
    kws = (
        tuple(topic_config.get("keywords_hi", []))
        + tuple(topic_config.get("keywords_en", []))
        + tuple(topic_config.get("keywords_hinglish", []))
    )
    pat = _compile(kws)
    return bool(pat and pat.search(text))


def topic_guard(text: str, config: Optional[Dict] = None) -> Dict:
    """
    Returns:
      needs_permission: bool
      blocked: bool
      triggered_topics: list[str]
    """
    result = {"needs_permission": False, "blocked": False, "triggered_topics": []}
    if not text:
        return result

    config = config or {}
    topics = config.get("sensitive_topics", DEFAULT_SENSITIVE_TOPICS)
    default_action = config.get("policy", {}).get("sensitive_topic_action", "permission")

    for name, tcfg in topics.items():
        if not check_topic(text, name, tcfg):
            continue
        result["triggered_topics"].append(name)
        action = tcfg.get("action", default_action)
        if action == "block":
            result["blocked"] = True
        else:
            result["needs_permission"] = True

    return result