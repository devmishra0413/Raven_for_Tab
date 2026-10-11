"""RAVEN Memory - exceptions. Messages never contain fact content."""
from __future__ import annotations


class MemoryError_(Exception):
    """Base class: callers can catch this one type."""


class MemoryStoreError(MemoryError_):
    """Storage/IO/database problem."""


class FactNotFound(MemoryError_):
    """No fact with the given id."""


class EntityNotFound(MemoryError_):
    """No entity with the given id."""


class ValidationError(MemoryError_):
    """Input validation failed."""