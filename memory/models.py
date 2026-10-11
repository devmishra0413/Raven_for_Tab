# RAVEN Memory - Data Models

from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class Fact:
    """A single stored fact / preference / note."""
    id: int
    content: str
    category: str = "other"
    sensitivity: int = 0          # 1 = never goes to cloud
    status: str = "confirmed"     # confirmed | pending
    source: str = "user"          # user | auto
    created_at: str = ""
    updated_at: str = ""

    def __repr__(self) -> str:
        # Never expose content in repr (log-safe)
        return f"Fact(id={self.id}, category={self.category!r}, sensitivity={self.sensitivity})"

    __str__ = __repr__


@dataclass
class Entity:
    """A known entity (person, place, org, etc.)."""
    id: int
    name: str
    type: str = "person"
    aliases: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_sanitize_dict(self) -> dict:
        """Format accepted by privacy.sanitize(entities=[...])."""
        return {"name": self.name, "aliases": self.aliases, "type": self.type}

    def __repr__(self) -> str:
        return f"Entity(id={self.id}, name={self.name!r}, type={self.type!r})"

    __str__ = __repr__


@dataclass
class Episode:
    """A conversation summary / episode."""
    id: int
    summary: str
    created_at: str = ""

    def __repr__(self) -> str:
        return f"Episode(id={self.id})"

    __str__ = __repr__
