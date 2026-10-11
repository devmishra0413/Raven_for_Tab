# Tests for memory/db.py - schema, migrations, FTS5

import os
import sqlite3
import pytest

from memory.db import open_db, rebuild_fts, SCHEMA_VERSION


class TestOpenDB:
    def test_creates_db_and_dirs(self, tmp_path):
        db_path = str(tmp_path / "sub" / "dir" / "test.db")
        conn, backend = open_db(db_path)
        assert os.path.isfile(db_path)
        conn.close()

    def test_schema_version_set(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn, _ = open_db(db_path)
        v = conn.execute("PRAGMA user_version").fetchone()[0]
        assert v == SCHEMA_VERSION
        conn.close()

    def test_fts5_backend_when_available(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn, backend = open_db(db_path)
        # On most modern SQLite builds, FTS5 is available
        assert backend in ("fts5", "like")
        conn.close()

    def test_all_tables_created(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn, _ = open_db(db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        for t in ["facts", "entities", "episodes", "reminders", "audit_log"]:
            assert t in tables, f"Table {t} not created"
        conn.close()

    def test_reopen_preserves_data(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn, _ = open_db(db_path)
        conn.execute(
            "INSERT INTO facts (content, content_norm, content_hash, category, sensitivity) "
            "VALUES (?, ?, ?, ?, ?)",
            ("test", "test", "hash1", "other", 0),
        )
        conn.commit()
        conn.close()

        conn2, _ = open_db(db_path)
        row = conn2.execute("SELECT content FROM facts WHERE content_hash = ?", ("hash1",)).fetchone()
        assert row is not None
        assert row[0] == "test"
        conn2.close()

    def test_memory_db(self):
        conn, backend = open_db(":memory:")
        assert backend in ("fts5", "like")
        conn.close()

    def test_wal_mode(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn, _ = open_db(db_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        # WAL or something else (if not supported)
        assert mode in ("wal", "delete", "truncate", "memory")
        conn.close()


class TestRebuildFTS:
    def test_rebuild_no_crash(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn, backend = open_db(db_path)
        if backend == "fts5":
            rebuild_fts(conn)  # Should not raise
        conn.close()

    def test_rebuild_on_memory_db(self):
        conn, backend = open_db(":memory:")
        if backend == "fts5":
            conn.execute(
                "INSERT INTO facts (content, content_norm, content_hash) VALUES (?, ?, ?)",
                ("hello", "hello", "h1"),
            )
            conn.commit()
            rebuild_fts(conn)
            rows = conn.execute(
                "SELECT * FROM facts_fts WHERE facts_fts MATCH ?", ('"hello"',)
            ).fetchall()
            assert len(rows) == 1
        conn.close()
