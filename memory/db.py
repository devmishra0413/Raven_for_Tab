"""RAVEN Memory - database layer: connection, schema, migrations, FTS5.

The DB file is NOT encrypted (known limitation); it is only chmod 0600.
"""
from __future__ import annotations

import os
import sqlite3
import stat

from .text_utils import DEVANAGARI_MARKS

SCHEMA_VERSION = 4  # v2: Devanagari FTS; v3: audit_log gets status/model/tokens/latency; v4: schedules table

# Constant (no user data) tokenizer spec. remove_diacritics 0 keeps nukta etc.
FTS_TOKENIZE = f"unicode61 remove_diacritics 0 tokenchars '{DEVANAGARI_MARKS}'"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    content_norm TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    category TEXT DEFAULT 'other',
    sensitivity INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'confirmed',
    source TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'person',
    aliases TEXT DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    due_at TEXT,
    done INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    kind TEXT,
    payload_hash TEXT,
    sanitized_payload TEXT,
    approved INTEGER,
    status TEXT,
    model TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms INTEGER
);
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    trigger_at TEXT,
    repeat_minutes INTEGER,
    payload TEXT NOT NULL,
    last_run_at TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
CREATE INDEX IF NOT EXISTS idx_facts_status ON facts(status);
CREATE INDEX IF NOT EXISTS idx_facts_sensitivity ON facts(sensitivity);
CREATE INDEX IF NOT EXISTS idx_schedules_enabled ON schedules(enabled);
CREATE INDEX IF NOT EXISTS idx_schedules_trigger_at ON schedules(trigger_at);
"""

_FTS5_SQL = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    content_norm, content=facts, content_rowid=id,
    tokenize="{FTS_TOKENIZE}"
);
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, content_norm) VALUES (new.id, new.content_norm);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content_norm) VALUES('delete', old.id, old.content_norm);
END;
CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content_norm) VALUES('delete', old.id, old.content_norm);
    INSERT INTO facts_fts(rowid, content_norm) VALUES (new.id, new.content_norm);
END;
"""
_TRIGGERS = ("facts_ai", "facts_ad", "facts_au")

_AUDIT_V3_COLUMNS = (
    ("status", "TEXT"),
    ("model", "TEXT"),
    ("prompt_tokens", "INTEGER"),
    ("completion_tokens", "INTEGER"),
    ("latency_ms", "INTEGER"),
)


def default_db_path() -> str:
    """<project root>/data/raven.db (project root = parent of this package)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "data", "raven.db")


def harden_permissions(path: str) -> None:
    """chmod 0600 on the DB and its -wal/-shm files, where the OS allows."""
    if path == ":memory:":
        return
    for p in (path, path + "-wal", path + "-shm"):
        try:
            if os.path.exists(p):
                os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
        except (OSError, AttributeError):
            pass


def _fts_ok(conn: sqlite3.Connection) -> bool:
    """FTS5 present AND the Devanagari tokenizer really works in this build."""
    try:
        conn.execute(f'CREATE VIRTUAL TABLE temp.fts_probe USING fts5(x, tokenize="{FTS_TOKENIZE}")')
    except sqlite3.Error:
        return False
    try:
        conn.execute("INSERT INTO temp.fts_probe(x) VALUES (?)", ("राहुल प्रियंका किताबें",))
        def hits(q: str) -> int:
            return conn.execute(
                "SELECT count(*) FROM temp.fts_probe WHERE fts_probe MATCH ?", (q,)
            ).fetchone()[0]
        return (hits('"राहुल"') == 1 and hits('"प्रियंका"') == 1
                and hits('"किताबें"') == 1 and hits('"राह"') == 0)
    except sqlite3.Error:
        return False
    finally:
        try:
            conn.execute("DROP TABLE IF EXISTS temp.fts_probe")
        except sqlite3.Error:
            pass


def _drop_fts(conn: sqlite3.Connection) -> None:
    for t in _TRIGGERS:
        conn.execute(f"DROP TRIGGER IF EXISTS {t}")
    try:
        conn.execute("DROP TABLE IF EXISTS facts_fts")
    except sqlite3.Error:
        pass  # module missing: table can't be dropped here


def _setup_fts(conn: sqlite3.Connection, current_version: int) -> str:
    """Create/upgrade FTS. Returns 'fts5' or 'like'."""
    if current_version < 2:
        _drop_fts(conn)  # old plain-unicode61 index -> rebuild below
    if not _fts_ok(conn):
        _drop_fts(conn)  # triggers must not reference a missing module
        return "like"
    existed = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name = 'facts_fts'"
    ).fetchone() is not None
    conn.executescript(_FTS5_SQL)
    if not existed:
        conn.execute("INSERT INTO facts_fts(facts_fts) VALUES('rebuild')")
    return "fts5"


def rebuild_fts(conn: sqlite3.Connection) -> None:
    """Rebuild the FTS index from the facts table."""
    conn.execute("INSERT INTO facts_fts(facts_fts) VALUES('rebuild')")
    conn.commit()


def _migrate_audit_v3(conn: sqlite3.Connection) -> None:
    """v3: add audit columns to old DBs. Idempotent; existing rows are kept."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(audit_log)")}
    for name, decl in _AUDIT_V3_COLUMNS:
        if name not in have:
            conn.execute(f"ALTER TABLE audit_log ADD COLUMN {name} {decl}")


def open_db(db_path: str | None = None, busy_timeout_ms: int = 5000) -> tuple[sqlite3.Connection, str]:
    """Open/create the DB, apply schema + migrations.

    Returns (connection, backend) with backend 'fts5' or 'like'.
    Raises sqlite3.Error / OSError (the manager wraps them).
    """
    path = db_path or default_db_path()
    if path != ":memory:":
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        try:  # create private from the start (no world-readable window)
            os.close(os.open(path, os.O_CREAT | os.O_RDWR, 0o600))
        except OSError:
            pass

    conn = sqlite3.connect(path, timeout=busy_timeout_ms / 1000)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
        try:
            conn.execute("PRAGMA journal_mode = WAL")  # may silently stay 'delete'
        except sqlite3.Error:
            pass
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        if current > SCHEMA_VERSION:
            raise sqlite3.DatabaseError("database schema is newer than this code")
        conn.executescript(_SCHEMA_SQL)
        _migrate_audit_v3(conn)
        backend = _setup_fts(conn, current)
        if current < SCHEMA_VERSION:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    except BaseException:
        conn.close()
        raise
    harden_permissions(path)
    return conn, backend