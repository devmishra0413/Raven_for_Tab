# Shared fixtures for memory tests

import os
import pytest
import tempfile

from memory.manager import MemoryManager


@pytest.fixture
def tmp_db(tmp_path):
    """Return a temporary DB path (file does not exist yet)."""
    return str(tmp_path / "test_raven.db")


@pytest.fixture
def mm(tmp_db):
    """A fresh MemoryManager with a temp DB."""
    m = MemoryManager(db_path=tmp_db)
    yield m
    m.close()


@pytest.fixture
def mm_like(tmp_db):
    """MemoryManager forced to use LIKE backend for testing."""
    m = MemoryManager(db_path=tmp_db)
    # Force LIKE backend by dropping FTS table
    try:
        m._conn.execute("DROP TABLE IF EXISTS facts_fts")
        m._conn.execute("DROP TRIGGER IF EXISTS facts_ai")
        m._conn.execute("DROP TRIGGER IF EXISTS facts_ad")
        m._conn.execute("DROP TRIGGER IF EXISTS facts_au")
        m._conn.commit()
    except Exception:
        pass
    m._search_backend = "like"
    yield m
    m.close()
