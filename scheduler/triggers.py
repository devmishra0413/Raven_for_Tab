"""Trigger engine: fixed condition/action dicts. NEVER eval/exec."""
import json
import logging
import subprocess
from datetime import timedelta

log = logging.getLogger(__name__)


def _check_pending_facts_gt_5(eng) -> bool:
    try:
        pending = eng.memory.list(status="pending", limit=20)
        return len([f for f in pending if not getattr(f, "sensitivity", 0)]) > 5
    except Exception:
        return False


def _check_daily(eng) -> bool:
    return True  # once/day is enforced by the 24h cooldown in evaluate_triggers


def _check_reminders_due_today(eng) -> bool:
    from scheduler.briefing import _fetch_reminders_due_today
    return len(_fetch_reminders_due_today(eng.memory, eng.config)) > 0


def _action_notify(eng) -> None:
    from scheduler.jobs import termux_api_available
    if not termux_api_available():
        return
    try:
        subprocess.run(["termux-notification", "--title", "RAVEN Alert",
                        "--content", "You have pending items in RAVEN"],
                       capture_output=True, timeout=5)
    except Exception as e:
        log.warning(f"Notification failed: {type(e).__name__}")


def _action_briefing(eng) -> None:
    from scheduler.jobs import run_briefing
    run_briefing({"scheduled_time": "trigger"}, eng.memory, eng.config)


ALLOWED_CONDITIONS = {
    "pending_facts_gt_5": _check_pending_facts_gt_5,
    "daily": _check_daily,
    "reminders_due_today": _check_reminders_due_today,
}
ALLOWED_ACTIONS = {
    "notify": _action_notify,
    "briefing": _action_briefing,
}


class TriggerEngine:
    def __init__(self, memory, config: dict):
        self.memory = memory
        self.config = config

    def check_condition(self, condition: str) -> bool:
        fn = ALLOWED_CONDITIONS.get(condition)
        if fn is None:
            log.warning("Unknown trigger condition, skipped")
            return False
        return bool(fn(self))

    def execute_action(self, action: str) -> None:
        fn = ALLOWED_ACTIONS.get(action)
        if fn is None:
            log.warning("Unknown trigger action, skipped")
            return
        fn(self)

    def evaluate_triggers(self, conn) -> None:
        """Called every scheduler cycle. Each trigger fires at most once per 24h."""
        from scheduler.engine import utc_now, parse_iso
        now = utc_now()
        rows = conn.execute(
            "SELECT id, payload, last_run_at FROM schedules WHERE kind='trigger' AND enabled=1"
        ).fetchall()
        for row in rows:
            try:
                last = parse_iso(row["last_run_at"])
                if last and now - last < timedelta(hours=24):
                    continue
                p = json.loads(row["payload"])
                if self.check_condition(p.get("condition", "")):
                    self.execute_action(p.get("action", ""))
                    conn.execute("UPDATE schedules SET last_run_at=? WHERE id=?",
                                 (now.isoformat(), row["id"]))
                    conn.commit()
            except Exception as e:
                log.warning(f"Trigger {row['id']} failed: {type(e).__name__}")