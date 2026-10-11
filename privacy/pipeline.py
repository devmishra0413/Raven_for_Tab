# RAVEN Privacy Core - Pipeline
# Orchestrates all privacy filters

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from .vault import Vault
from .normalize import normalize_spoken_digits, normalize_for_detection
from .topic_guard import topic_guard
from .regex_filter import regex_filter
from .entity_filter import entity_filter
from .failsafe import failsafe
from .config import merge_config


@dataclass
class GuardResult:
    """Result of the privacy sanitization pipeline."""
    clean_text: str
    blocked: bool
    needs_permission: bool
    reason: Optional[str]
    vault: Vault
    findings: List[Dict[str, Any]]  # type + placeholder only


def _blocked(vault: Vault, reason: str, needs_permission: bool = False) -> GuardResult:
    # clean_text is empty on purpose: a blocked message must never reach the cloud
    return GuardResult(
        clean_text="",
        blocked=True,
        needs_permission=needs_permission,
        reason=reason,
        vault=vault,
        findings=vault.get_findings(),
    )


def sanitize(
    text: str,
    entities: Optional[List] = None,
    config: Optional[Dict] = None,
    vault: Optional[Vault] = None,          # NEW (optional)
) -> GuardResult:
    """
    Order:
    0. normalize  - spoken digits + Devanagari digits -> ASCII
    1. topic_guard - sensitive topics (block / needs permission)
    2. regex_filter - phone, email, aadhaar, pan, card, ...
    3. entity_filter - user-supplied names/places
    4. failsafe - last check on the masked text
    """
    vault = vault if vault is not None else Vault()

    if not text:
        return GuardResult("", False, False, None, vault, [])

    cfg = merge_config(config)

    # 0. Normalize (once, first; length may change, so nothing before this)
    text = normalize_for_detection(normalize_spoken_digits(text))

    # 1. Topic guard
    topic = topic_guard(text, cfg)
    needs_permission = topic["needs_permission"]
    reason = None

    if topic["triggered_topics"]:
        topics_cfg = cfg.get("sensitive_topics", {})
        default_action = cfg.get("policy", {}).get("sensitive_topic_action", "permission")
        # prefer the topic that actually blocks as the reason
        chosen = next(
            (t for t in topic["triggered_topics"]
             if topics_cfg.get(t, {}).get("action", default_action) == "block"),
            topic["triggered_topics"][0],
        )
        reason = f"topic:{chosen}"

    if topic["blocked"]:
        return _blocked(vault, reason or "topic:blocked", needs_permission)

    # 2. Regex filter
    masked, _ = regex_filter(text, vault)

    # 3. Entity filter
    masked, _ = entity_filter(masked, entities=entities, vault=vault)

    # 4. Failsafe
    fs = failsafe(masked, cfg)
    if fs["blocked"]:
        return _blocked(vault, fs["reason"], needs_permission)

    return GuardResult(
        clean_text=masked,
        blocked=False,
        needs_permission=needs_permission,
        reason=reason,
        vault=vault,
        findings=vault.get_findings(),
    )