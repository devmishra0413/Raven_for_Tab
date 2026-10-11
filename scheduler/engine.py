"""Scheduler engine: background thread polling the schedules table."""
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

try:
    import fcntl
except ImportError:  # non-POSIX
    fcntl = None

log = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(s) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def get_db_path(memory, config: dict) -> str:
    return config.get("db_path") or getattr(memory, "db_path", None) or "data/raven.db"


def connect(memory, config: dict) -> sqlite3.Connection:
    """New connection per call/thread."""
    conn = sqlite3.connect(get_db_path(memory, config), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


class SchedulerEngine:
    def __init__(self, memory, config: dict):
        self.memory = memory
        self.config = config
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        self._lock_fh = None
        self._check_interval = config.get("check_interval_seconds", 30)

    # ---- lifecycle ----
    def _acquire_lock(self) -> bool:
        """One scheduler per DB (CLI + API server must not both fire jobs)."""
        if fcntl is None:
            return True
        try:
            self._lock_fh = open(get_db_path(self.memory, self.config) + ".sched.lock", "w")
            fcntl.flock(self._lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def start(self) -> None:
        if self._running:
            return
        if not self._acquire_lock():
            log.info("Another process runs the scheduler; this one is API-only")
            return
        try:
            self._ensure_briefing_job()
        except Exception as e:
            log.warning(f"Briefing job setup failed: {type(e).__name__}")
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="SchedulerThread")
        self._thread.start()
        log.info("Scheduler started")

    def stop(self) -> None:
        if not self._running:
            return
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._running = False
        try:
            if self._lock_fh:
                self._lock_fh.close()
        except Exception:
            pass
        log.info("Scheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ---- public API ----
    def add_reminder(self, text: str, due_at: str, job_id: Optional[int] = None) -> int:
        """text must already be sanitized. due_at: ISO8601 UTC."""
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "INSERT INTO schedules (kind, trigger_at, repeat_minutes, payload, enabled) "
                "VALUES ('reminder', ?, NULL, ?, 1)",
                (due_at, json.dumps({"text": text, "original_job_id": job_id or 0})),
            )
            row_id = cur.lastrowid
            if not job_id:  # use the row id as the notification id
                conn.execute("UPDATE schedules SET payload = ? WHERE id = ?",
                             (json.dumps({"text": text, "original_job_id": row_id}), row_id))
            conn.commit()
            return row_id
        finally:
            conn.close()

    def cancel_job(self, job_id: int) -> None:
        conn = self._get_connection()
        try:
            conn.execute("UPDATE schedules SET enabled = 0 WHERE id = ?", (job_id,))
            conn.commit()
        finally:
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        return connect(self.memory, self.config)

    # ---- briefing auto-create ----
    def _ensure_briefing_job(self) -> None:
        if not self.config.get("briefing_enabled", True):
            return
        conn = self._get_connection()
        try:
            if conn.execute("SELECT 1 FROM schedules WHERE kind='briefing' AND enabled=1").fetchone():
                return
            hh, mm = str(self.config.get("briefing_time", "08:00")).split(":")
            off = timedelta(hours=float(self.config.get("timezone_offset_hours", 0)))
            now_local = utc_now() + off
            target = now_local.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            if target <= now_local:
                target += timedelta(days=1)
            conn.execute(
                "INSERT INTO schedules (kind, trigger_at, repeat_minutes, payload, enabled) "
                "VALUES ('briefing', ?, 1440, ?, 1)",
                ((target - off).isoformat(), json.dumps({"scheduled_time": f"{hh}:{mm}"})),
            )
            conn.commit()
        finally:
            conn.close()

    # ---- loop ----
    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._check_and_run_jobs()
            except Exception as e:
                log.error(f"Scheduler loop error: {type(e).__name__}")
            self._stop_event.wait(self._check_interval)

    @staticmethod
    def _is_due(job, now: datetime) -> bool:
        trig = parse_iso(job["trigger_at"])
        last = parse_iso(job["last_run_at"])
        rep = job["repeat_minutes"]
        if trig is not None:
            return trig <= now
        if rep:
            return last is None or last + timedelta(minutes=rep) <= now
        return False

    def _check_and_run_jobs(self) -> None:
        now = utc_now()
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT id, kind, trigger_at, repeat_minutes, payload, last_run_at "
                "FROM schedules WHERE enabled = 1 AND kind != 'trigger'"
            ).fetchall()
            for job in rows:
                try:
                    if self._is_due(job, now):
                        self._execute_job(job, now, conn)
                except Exception as e:
                    log.warning(f"Job {job['id']} failed: {type(e).__name__}")
            try:
                from scheduler.triggers import TriggerEngine
                TriggerEngine(self.memory, self.config).evaluate_triggers(conn)
            except Exception as e:
                log.warning(f"Trigger evaluation failed: {type(e).__name__}")
        finally:
            conn.close()

    def _execute_job(self, job, now: datetime, conn: sqlite3.Connection) -> None:
        from scheduler.jobs import run_reminder, run_briefing
        kind = job["kind"]
        payload = json.loads(job["payload"])
        rep = job["repeat_minutes"]
        trig = parse_iso(job["trigger_at"])

        if kind == "reminder":
            run_reminder(payload)
        elif kind == "briefing":
            if self.config.get("briefing_enabled", True):
                run_briefing(payload, self.memory, self.config)
        else:
            log.warning("Unknown job kind")
            return

        now_iso = now.isoformat()
        if rep:
            if trig is not None:
                nxt = trig
                while nxt <= now:
                    nxt += timedelta(minutes=rep)
                conn.execute("UPDATE schedules SET last_run_at=?, trigger_at=? WHERE id=?",
                             (now_iso, nxt.isoformat(), job["id"]))
            else:
                conn.execute("UPDATE schedules SET last_run_at=? WHERE id=?", (now_iso, job["id"]))
        else:
            conn.execute("UPDATE schedules SET last_run_at=?, enabled=0 WHERE id=?",
                         (now_iso, job["id"]))
        conn.commit()