"""RAVEN Memory - MemoryManager: facts, entities, episodes, search, export/import.

Only MemoryError_ subclasses leave public methods. No fact content is ever put
in exceptions or logs (ids, counts and exception type names only).
"""
from __future__ import annotations

import functools
import json
import logging
import os
import sqlite3
from typing import Any, Callable

from . import _privacy
from .db import harden_permissions, open_db
from .exceptions import (EntityNotFound, FactNotFound, MemoryError_,
                         MemoryStoreError, ValidationError)
from .models import Entity, Episode, Fact
from .text_utils import (clean_content, content_hash, normalize_content,
                         sanitize_fts_query, sanitize_like_tokens)

log = logging.getLogger("raven.memory")

VALID_CATEGORIES = {"preference", "person", "task", "event", "other"}
VALID_STATUSES = {"confirmed", "pending"}
VALID_SOURCES = {"user", "auto"}
EXPORT_VERSION = 1

MAX_NAME_LEN = 100
MAX_TYPE_LEN = 30
MAX_ALIASES = 20
MAX_EPISODE_LEN = 2000
MAX_RECORDS_PER_SECTION = 20000

DEFAULT_CONFIG = {
    "db_path": None,
    "max_content_length": 500,
    "busy_timeout_ms": 5000,
    "max_import_bytes": 5 * 1024 * 1024,
}


# ---------------------------------------------------------------- helpers
def _guarded(fn: Callable) -> Callable:
    """Public-method wrapper: nothing but MemoryError_ subclasses escapes."""
    @functools.wraps(fn)
    def wrapper(self: "MemoryManager", *a: Any, **kw: Any):
        try:
            return fn(self, *a, **kw)
        except MemoryError_:
            raise
        except (sqlite3.Error, OSError) as exc:
            _rollback(self)
            log.warning("%s failed: %s", fn.__name__, type(exc).__name__)
            raise MemoryStoreError(f"{fn.__name__} failed") from exc
        except Exception as exc:  # unexpected bug: still must not leak
            _rollback(self)
            log.error("%s crashed: %s", fn.__name__, type(exc).__name__)
            raise MemoryStoreError(f"{fn.__name__} failed unexpectedly") from None
    return wrapper


def _rollback(m: "MemoryManager") -> None:
    try:
        m._conn.rollback()
    except Exception:
        pass


def _req_str(v: Any, name: str) -> str:
    if not isinstance(v, str):
        raise ValidationError(f"{name} must be a string")
    return v


def _req_id(v: Any) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValidationError("id must be an integer")
    return v


def _clamp(v: Any, name: str, lo: int, hi: int) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValidationError(f"{name} must be an integer")
    return max(lo, min(v, hi))


def _row_to_fact(r: sqlite3.Row) -> Fact:
    return Fact(id=r["id"], content=r["content"], category=r["category"] or "other",
                sensitivity=r["sensitivity"], status=r["status"], source=r["source"],
                created_at=r["created_at"], updated_at=r["updated_at"])


def _row_to_entity(r: sqlite3.Row) -> Entity:
    try:
        aliases = json.loads(r["aliases"] or "[]")
    except (ValueError, TypeError):
        aliases = []
    if not isinstance(aliases, list):
        aliases = []
    return Entity(id=r["id"], name=r["name"], type=r["type"] or "person",
                  aliases=[a for a in aliases if isinstance(a, str)],
                  created_at=r["created_at"], updated_at=r["updated_at"])


def _clean_aliases(aliases: Any) -> list[str]:
    if aliases is None:
        return []
    if not isinstance(aliases, (list, tuple)):
        raise ValidationError("aliases must be a list of strings")
    out: list[str] = []
    seen: set[str] = set()
    for a in aliases:
        if not isinstance(a, str):
            raise ValidationError("aliases must be a list of strings")
        a = clean_content(a)
        if not a:
            continue
        if len(a) > MAX_NAME_LEN:
            raise ValidationError("alias too long")
        key = normalize_content(a)
        if key not in seen:
            seen.add(key)
            out.append(a)
    if len(out) > MAX_ALIASES:
        raise ValidationError("too many aliases")
    return out


# ---------------------------------------------------------------- manager
class MemoryManager:
    """Local SQLite memory. Use as a context manager.

    DB is NOT encrypted (known limitation); file mode is 0600 where possible.
    """

    def __init__(self, db_path: str | None = None, config: dict | None = None):
        self._config = {**DEFAULT_CONFIG, **(config or {})}
        self.last_import_report: dict[str, int] = {}
        path = db_path or self._config.get("db_path")
        try:
            self._conn, self._search_backend = open_db(path, int(self._config["busy_timeout_ms"]))
        except (sqlite3.Error, OSError) as exc:
            log.error("open failed: %s", type(exc).__name__)
            raise MemoryStoreError("Cannot open database") from exc
        self._path = path
        self._closed = False

    @property
    def search_backend(self) -> str:
        return self._search_backend

    def __enter__(self) -> "MemoryManager":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the connection (safe to call twice)."""
        if getattr(self, "_closed", True):
            return
        self._closed = True
        try:
            self._conn.close()
        except sqlite3.Error:
            pass
        if self._path:
            harden_permissions(self._path)

    # ------------------------------------------------------ validation
    def _validate_content(self, content: Any) -> str:
        _req_str(content, "content")
        content = clean_content(content)
        if not normalize_content(content):
            raise ValidationError("Content must not be empty")
        max_len = int(self._config.get("max_content_length", 500))
        if len(content) > max_len:
            raise ValidationError(f"Content exceeds {max_len} characters")
        return content

    @staticmethod
    def _choice(v: Any, allowed: set[str], default: str, name: str) -> str:
        v = default if v is None else v
        _req_str(v, name)
        v = v.lower().strip() or default
        if v not in allowed:
            raise ValidationError(f"Invalid {name}")
        return v

    # ------------------------------------------------------ facts
    def _fact_by_id(self, id: int) -> Fact | None:
        r = self._conn.execute("SELECT * FROM facts WHERE id = ?", (id,)).fetchone()
        return _row_to_fact(r) if r else None

    def _add_core(self, content: Any, category: Any, sensitivity: int | None,
                  source: Any, status: Any, commit: bool = True) -> tuple[Fact, bool]:
        """Insert or dedupe. Returns (fact, created). Never lowers sensitivity."""
        content = self._validate_content(content)
        category = self._choice(category, VALID_CATEGORIES, "other", "category")
        status = self._choice(status, VALID_STATUSES, "confirmed", "status")
        source = self._choice(source, VALID_SOURCES, "user", "source")
        norm, chash = normalize_content(content), content_hash(content)
        sens = _privacy.looks_sensitive(content) if sensitivity is None else int(bool(sensitivity))

        row = self._conn.execute("SELECT * FROM facts WHERE content_hash = ?", (chash,)).fetchone()
        if row is None:
            try:
                cur = self._conn.execute(
                    "INSERT INTO facts (content, content_norm, content_hash, category,"
                    " sensitivity, status, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (content, norm, chash, category, sens, status, source))
                if commit:
                    self._conn.commit()
                return self._fact_by_id(cur.lastrowid), True  # type: ignore[arg-type]
            except sqlite3.IntegrityError:
                if not commit:
                    raise
                self._conn.rollback()  # lost a race: fall through to dedupe path
                row = self._conn.execute("SELECT * FROM facts WHERE content_hash = ?", (chash,)).fetchone()
                if row is None:
                    raise

        existing = _row_to_fact(row)
        sets: list[str] = []
        params: list[Any] = []
        if sens > existing.sensitivity:          # raise only, never lower
            sets.append("sensitivity = ?")
            params.append(sens)
        if status == "confirmed" and existing.status == "pending":
            sets.append("status = ?")
            params.append("confirmed")
        if sets:
            sets.append("updated_at = strftime('%Y-%m-%dT%H:%M:%S', 'now')")
            params.append(existing.id)
            self._conn.execute(f"UPDATE facts SET {', '.join(sets)} WHERE id = ?", params)
            if commit:
                self._conn.commit()
            existing = self._fact_by_id(existing.id)  # type: ignore[assignment]
        return existing, False

    @_guarded
    def add(self, content: str, category: str = "other", sensitivity: int | None = None,
            source: str = "user", status: str = "confirmed") -> Fact:
        """Add a fact; same normalized content returns the existing fact.

        sensitivity=None -> auto (Phase 1 sanitize: topic/regex hit => 1).
        Explicit value wins for NEW facts. On a duplicate the stored flag can
        only be raised, never lowered; a pending duplicate added as confirmed
        becomes confirmed.
        """
        return self._add_core(content, category, sensitivity, source, status)[0]

    @_guarded
    def get(self, id: int) -> Fact:
        _req_id(id)
        f = self._fact_by_id(id)
        if f is None:
            raise FactNotFound(f"Fact id={id} not found")
        return f

    @_guarded
    def update(self, id: int, content: str | None = None, category: str | None = None,
               sensitivity: int | None = None) -> Fact:
        """Update given fields. Changing content re-runs auto-sensitivity and
        can only raise the flag unless `sensitivity` is passed explicitly."""
        fact = self.get(id)
        sets: list[str] = []
        params: list[Any] = []
        new_sens = None if sensitivity is None else int(bool(sensitivity))

        if content is not None:
            content = self._validate_content(content)
            chash = content_hash(content)
            dup = self._conn.execute(
                "SELECT id FROM facts WHERE content_hash = ? AND id != ?", (chash, id)).fetchone()
            if dup:
                raise ValidationError("Updated content would duplicate another fact")
            sets += ["content = ?", "content_norm = ?", "content_hash = ?"]
            params += [content, normalize_content(content), chash]
            if new_sens is None:
                new_sens = 1 if (fact.sensitivity or _privacy.looks_sensitive(content)) else 0
        if category is not None:
            sets.append("category = ?")
            params.append(self._choice(category, VALID_CATEGORIES, "other", "category"))
        if new_sens is not None and new_sens != fact.sensitivity:
            sets.append("sensitivity = ?")
            params.append(new_sens)
        if not sets:
            return fact
        sets.append("updated_at = strftime('%Y-%m-%dT%H:%M:%S', 'now')")
        params.append(id)
        self._conn.execute(f"UPDATE facts SET {', '.join(sets)} WHERE id = ?", params)
        self._conn.commit()
        return self.get(id)

    @_guarded
    def delete(self, id: int) -> None:
        _req_id(id)
        cur = self._conn.execute("DELETE FROM facts WHERE id = ?", (id,))
        self._conn.commit()
        if cur.rowcount == 0:
            raise FactNotFound(f"Fact id={id} not found")

    @_guarded
    def confirm(self, id: int) -> Fact:
        """pending -> confirmed."""
        fact = self.get(id)
        if fact.status == "confirmed":
            return fact
        self._conn.execute(
            "UPDATE facts SET status = 'confirmed',"
            " updated_at = strftime('%Y-%m-%dT%H:%M:%S', 'now') WHERE id = ?", (id,))
        self._conn.commit()
        return self.get(id)

    @_guarded
    def list(self, limit: int = 50, offset: int = 0, category: str | None = None,
             status: str | None = None) -> list[Fact]:
        limit = _clamp(limit, "limit", 0, 1000)
        offset = _clamp(offset, "offset", 0, 10**9)
        sql = "SELECT * FROM facts WHERE 1=1"
        params: list[Any] = []
        if category is not None:
            sql += " AND category = ?"
            params.append(self._choice(category, VALID_CATEGORIES, "other", "category"))
        if status is not None:
            sql += " AND status = ?"
            params.append(self._choice(status, VALID_STATUSES, "confirmed", "status"))
        sql += " ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        return [_row_to_fact(r) for r in self._conn.execute(sql, params).fetchall()]

    # ------------------------------------------------------ search
    @_guarded
    def search(self, query: str, k: int = 5, include_sensitive: bool = True,
               include_pending: bool = False) -> list[Fact]:
        """Keyword search, most relevant first. Empty query -> []."""
        _req_str(query, "query")
        k = _clamp(k, "k", 0, 100)
        if k == 0 or not query.strip():
            return []
        if self._search_backend == "fts5":
            try:
                return self._search_fts5(query, k, include_sensitive, include_pending)
            except sqlite3.OperationalError as exc:
                log.warning("fts5 search failed, using LIKE: %s", type(exc).__name__)
        return self._search_like(query, k, include_sensitive, include_pending)

    @staticmethod
    def _filters(alias: str, include_sensitive: bool, include_pending: bool) -> str:
        sql = ""
        if not include_sensitive:
            sql += f" AND {alias}sensitivity = 0"
        if not include_pending:
            sql += f" AND {alias}status = 'confirmed'"
        return sql

    def _search_fts5(self, query: str, k: int, inc_s: bool, inc_p: bool) -> list[Fact]:
        q = sanitize_fts_query(query)
        if not q:
            return []
        sql = ("SELECT f.* FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid"
               " WHERE facts_fts MATCH ?" + self._filters("f.", inc_s, inc_p)
               + " ORDER BY bm25(facts_fts), f.id LIMIT ?")
        return [_row_to_fact(r) for r in self._conn.execute(sql, (q, k)).fetchall()]

    def _search_like(self, query: str, k: int, inc_s: bool, inc_p: bool) -> list[Fact]:
        pats = sanitize_like_tokens(query)
        if not pats:
            return []
        cond = " OR ".join(["content_norm LIKE ?"] * len(pats))
        score = " + ".join(["(content_norm LIKE ?)"] * len(pats))
        sql = (f"SELECT * FROM facts WHERE ({cond})" + self._filters("", inc_s, inc_p)
               + f" ORDER BY ({score}) DESC, updated_at DESC, id LIMIT ?")
        rows = self._conn.execute(sql, pats + pats + [k]).fetchall()
        return [_row_to_fact(r) for r in rows]

    # ------------------------------------------------------ entities
    def _entity_by_id(self, id: int) -> Entity | None:
        r = self._conn.execute("SELECT * FROM entities WHERE id = ?", (id,)).fetchone()
        return _row_to_entity(r) if r else None

    def _clean_name(self, name: Any) -> str:
        _req_str(name, "name")
        name = clean_content(name)
        if not name:
            raise ValidationError("Entity name must not be empty")
        if len(name) > MAX_NAME_LEN:
            raise ValidationError("Entity name too long")
        return name

    def _clean_type(self, type_: Any) -> str:
        type_ = "person" if type_ is None else type_
        _req_str(type_, "type")
        type_ = clean_content(type_).casefold() or "person"
        if len(type_) > MAX_TYPE_LEN:
            raise ValidationError("Entity type too long")
        return type_

    def _add_entity_core(self, name: Any, type_: Any, aliases: Any,
                         commit: bool = True) -> tuple[Entity, bool]:
        name = self._clean_name(name)
        type_ = self._clean_type(type_)
        al = _clean_aliases(aliases)
        key = normalize_content(name)
        for r in self._conn.execute("SELECT * FROM entities").fetchall():
            if normalize_content(r["name"]) == key:      # same name: merge aliases
                ent = _row_to_entity(r)
                have = {normalize_content(a) for a in ent.aliases}
                merged = ent.aliases + [a for a in al if normalize_content(a) not in have]
                if len(merged) > MAX_ALIASES:
                    raise ValidationError("too many aliases")
                if merged != ent.aliases:
                    self._conn.execute(
                        "UPDATE entities SET aliases = ?,"
                        " updated_at = strftime('%Y-%m-%dT%H:%M:%S', 'now') WHERE id = ?",
                        (json.dumps(merged, ensure_ascii=False), ent.id))
                    if commit:
                        self._conn.commit()
                return self._entity_by_id(ent.id), False  # type: ignore[return-value]
        cur = self._conn.execute("INSERT INTO entities (name, type, aliases) VALUES (?, ?, ?)",
                                 (name, type_, json.dumps(al, ensure_ascii=False)))
        if commit:
            self._conn.commit()
        return self._entity_by_id(cur.lastrowid), True  # type: ignore[arg-type,return-value]

    @_guarded
    def add_entity(self, name: str, type: str = "person",
                   aliases: list[str] | None = None) -> Entity:
        """Add an entity; an existing same-name entity gets the aliases merged."""
        return self._add_entity_core(name, type, aliases)[0]

    @_guarded
    def update_entity(self, id: int, name: str | None = None, type: str | None = None,
                      aliases: list[str] | None = None) -> Entity:
        _req_id(id)
        ent = self._entity_by_id(id)
        if ent is None:
            raise EntityNotFound(f"Entity id={id} not found")
        sets: list[str] = []
        params: list[Any] = []
        if name is not None:
            sets.append("name = ?")
            params.append(self._clean_name(name))
        if type is not None:
            sets.append("type = ?")
            params.append(self._clean_type(type))
        if aliases is not None:
            sets.append("aliases = ?")
            params.append(json.dumps(_clean_aliases(aliases), ensure_ascii=False))
        if not sets:
            return ent
        sets.append("updated_at = strftime('%Y-%m-%dT%H:%M:%S', 'now')")
        params.append(id)
        self._conn.execute(f"UPDATE entities SET {', '.join(sets)} WHERE id = ?", params)
        self._conn.commit()
        return self._entity_by_id(id)  # type: ignore[return-value]

    @_guarded
    def delete_entity(self, id: int) -> None:
        _req_id(id)
        cur = self._conn.execute("DELETE FROM entities WHERE id = ?", (id,))
        self._conn.commit()
        if cur.rowcount == 0:
            raise EntityNotFound(f"Entity id={id} not found")

    @_guarded
    def entity_list(self) -> list[dict]:
        """[{"name","aliases","type"}] - the format Phase 1 sanitize() accepts."""
        rows = self._conn.execute("SELECT * FROM entities ORDER BY name, id").fetchall()
        return [_row_to_entity(r).to_sanitize_dict() for r in rows]

    # ------------------------------------------------------ episodes
    @_guarded
    def add_episode(self, summary: str) -> int:
        _req_str(summary, "summary")
        summary = clean_content(summary)
        if not summary:
            raise ValidationError("Episode summary must not be empty")
        if len(summary) > MAX_EPISODE_LEN:
            raise ValidationError("Episode summary too long")
        cur = self._conn.execute("INSERT INTO episodes (summary) VALUES (?)", (summary,))
        self._conn.commit()
        return int(cur.lastrowid)

    @_guarded
    def recent_episodes(self, n: int = 5) -> list[Episode]:
        n = _clamp(n, "n", 0, 1000)
        rows = self._conn.execute(
            "SELECT * FROM episodes ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        return [Episode(id=r["id"], summary=r["summary"], created_at=r["created_at"]) for r in rows]

    # ------------------------------------------------------ export / import
    @_guarded
    def export_json(self, path: str) -> int:
        """Write all data to JSON (mode 0600). WARNING: contains RAW private
        data, unencrypted. Returns number of records written."""
        _req_str(path, "path")
        data: dict[str, Any] = {"version": EXPORT_VERSION, "facts": [], "entities": [], "episodes": []}
        for r in self._conn.execute("SELECT * FROM facts ORDER BY id").fetchall():
            data["facts"].append({k: r[k] for k in ("content", "category", "sensitivity",
                                                     "status", "source", "created_at", "updated_at")})
        for r in self._conn.execute("SELECT * FROM entities ORDER BY id").fetchall():
            e = _row_to_entity(r)
            data["entities"].append({"name": e.name, "type": e.type, "aliases": e.aliases})
        for r in self._conn.execute("SELECT * FROM episodes ORDER BY id").fetchall():
            data["episodes"].append({"summary": r["summary"], "created_at": r["created_at"]})
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = path + ".tmp"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        return len(data["facts"]) + len(data["entities"]) + len(data["episodes"])

    @_guarded
    def import_json(self, path: str) -> int:
        """Import from an export file. Every record is validated; bad ones are
        skipped; nothing in the file is executed. Returns the number of NEW
        records; details in `self.last_import_report` (imported/duplicates/skipped).
        Sensitivity is never lowered: stored = max(file flag, auto-detect)."""
        _req_str(path, "path")
        try:
            size = os.path.getsize(path)
        except OSError as exc:
            raise MemoryStoreError("Cannot read import file") from exc
        if size > int(self._config["max_import_bytes"]):
            raise ValidationError("Import file too large")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError, RecursionError):
            raise MemoryStoreError("Import file unreadable or not valid JSON") from None
        if not isinstance(data, dict):
            raise ValidationError("Import file must contain a JSON object")
        ver = data.get("version")
        if isinstance(ver, bool) or not isinstance(ver, int) or not 1 <= ver <= EXPORT_VERSION:
            raise ValidationError("Unsupported export version")

        def section(key: str) -> list:
            v = data.get(key)
            return v[:MAX_RECORDS_PER_SECTION] if isinstance(v, list) else []

        new = dup = skipped = 0
        for item in section("facts"):
            if not isinstance(item, dict):
                skipped += 1
                continue
            try:
                content = self._validate_content(item.get("content"))
                cat = item.get("category")
                cat = cat if cat in VALID_CATEGORIES else "other"
                status = item.get("status")
                status = status if status in VALID_STATUSES else "confirmed"
                src = item.get("source")
                src = src if src in VALID_SOURCES else "user"
                sens = 1 if (bool(item.get("sensitivity", 0)) or _privacy.looks_sensitive(content)) else 0
                _, created = self._add_core(content, cat, sens, src, status, commit=False)
            except ValidationError:
                skipped += 1
                continue
            new, dup = (new + 1, dup) if created else (new, dup + 1)

        for item in section("entities"):
            if not isinstance(item, dict):
                skipped += 1
                continue
            al = item.get("aliases")
            al = [a for a in al if isinstance(a, str)] if isinstance(al, list) else []
            try:
                _, created = self._add_entity_core(item.get("name"), item.get("type"), al, commit=False)
            except ValidationError:
                skipped += 1
                continue
            new, dup = (new + 1, dup) if created else (new, dup + 1)

        for item in section("episodes"):
            s = item.get("summary") if isinstance(item, dict) else None
            if not isinstance(s, str):
                skipped += 1
                continue
            s = clean_content(s)
            if not s or len(s) > MAX_EPISODE_LEN:
                skipped += 1
                continue
            if self._conn.execute("SELECT 1 FROM episodes WHERE summary = ?", (s,)).fetchone():
                dup += 1
                continue
            self._conn.execute("INSERT INTO episodes (summary) VALUES (?)", (s,))
            new += 1

        self._conn.commit()
        self.last_import_report = {"imported": new, "duplicates": dup, "skipped": skipped}
        log.info("import done: new=%d dup=%d skipped=%d", new, dup, skipped)
        return new