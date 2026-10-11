"""Core errors for RAVEN Phase 3.

Messages are USER-FACING and must never contain raw user data, request or
response bodies, or the API key.
"""
from __future__ import annotations


class RavenError(Exception):
    """Base class: catch this one type for any RAVEN error."""


class ConfigError(RavenError):
    """Configuration problem (file, values, missing env var)."""


class VaultError(RavenError):
    """Vault operation failed."""


class PrivacyBlocked(RavenError):
    """Message blocked by privacy rules; it must not reach the cloud."""


class PermissionRequired(RavenError):
    """Sensitive topic needs the user's permission."""


class PreviewMismatch(RavenError):
    """Payload hash changed between preview and send."""


PreviewMissmatch = PreviewMismatch  # old misspelled name, kept as an alias


class CloudError(RavenError):
    """Cloud problem (network, auth, model unavailable, bad reply)."""


class SessionError(RavenError):
    """Session operation failed."""


class AuditError(RavenError):
    """Audit logging failed."""