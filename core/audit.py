"""Phase 3 audit logger: rows in the Phase 2 `audit_log` table.

Only SANITIZED payloads are stored. Errors never include payload text.
Needs the v3 migration in memory/db.py (adds: status, model, prompt_tokens,
completion_tokens, latency_ms).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from memory.db import open_db
from core.errors import AuditError

KINDS = {"cloud_send", "blocked", "cancelled", "error"}
_UPDATABLE = ("status", "model", "prompt_tokens", "completion_tokens", "latency_ms")


class AuditLogger:
    def __init__(self, db_path: str) -> None:
        try:
            self.conn, _ = open_db(db_path)
        except Exception as exc:
            raise AuditError("could not open audit database") from exc

    def log(self, kind: str, payload: str = "", payload_hash: str = "",
            status: Optional[str] = None) -> int:
        """Insert a row, return its id. Raises AuditError on any failure."""
        if kind not in KINDS:
            raise AuditError(f"unknown audit kind: {kind!r}")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        try:
            cur = self.conn.execute(
                "INSERT INTO audit_log (ts, kind, payload_hash, sanitized_payload, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (ts, kind, payload_hash or "", payload or "", status),
            )
            self.conn.commit()
            return int(cur.lastrowid)
        except Exception as exc:
            raise AuditError("failed to write audit log") from exc

    def update(self, row_id: int, **fields: Any) -> None:
        """Update status/model/tokens/latency of an existing row."""
        sets = {k: v for k, v in fields.items() if k in _UPDATABLE and v is not None}
        if not sets:
            return
        sql = "UPDATE audit_log SET " + ", ".join(f"{k} = ?" for k in sets) + " WHERE id = ?"
        try:
            self.conn.execute(sql, (*sets.values(), row_id))
            self.conn.commit()
        except Exception as exc:
            raise AuditError("failed to update audit log") from exc

    def recent(self, n: int = 10) -> list[dict]:
        """Last n rows, newest first (sanitized data only)."""
        n = max(1, min(int(n), 100))
        try:
            cur = self.conn.execute(
                "SELECT id, ts, kind, payload_hash, sanitized_payload, status, model, "
                "prompt_tokens, completion_tokens, latency_ms "
                "FROM audit_log ORDER BY id DESC LIMIT ?", (n,))
            return [dict(r) for r in cur.fetchall()]
        except Exception as exc:
            raise AuditError("failed to read audit log") from exc

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass