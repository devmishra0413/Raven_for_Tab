"""Daily briefing builder - local only, no cloud calls."""
import json
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)


def build_briefing(memory, config: dict) -> str:
    lines = ["=== RAVEN Daily Briefing ==="]

    if config.get("briefing_include_reminders", True):
        due = _fetch_reminders_due_today(memory, config)
        if due:
            lines.append(f"Reminders today: {len(due)}")
            for r in due[:5]:
                lines.append(f"  - {r['text'][:60]}")

    if config.get("briefing_include_facts", True):
        try:
            mx = int(config.get("briefing_max_facts", 5))
            pending = memory.list(status="pending", limit=mx * 3)
            # never include sensitive facts
            pending = [f for f in pending if not getattr(f, "sensitivity", 0)][:mx]
            if pending:
                lines.append(f"Pending facts to confirm: {len(pending)}")
                for f in pending:
                    lines.append(f"  [{f.id}] {f.content[:60]}")
        except Exception as e:
            log.warning(f"Pending facts fetch failed: {type(e).__name__}")

    lines.append("Open RAVEN to manage.")
    result = "\n".join(lines)
    return result[:497] + "..." if len(result) > 500 else result


def _fetch_reminders_due_today(memory, config: dict) -> list:
    """Reminders whose trigger_at falls in today's LOCAL day (config offset)."""
    from scheduler.engine import connect, parse_iso
    off = timedelta(hours=float(config.get("timezone_offset_hours", 0)))
    now_local = datetime.now(timezone.utc) + off
    start = now_local.replace(hour=0, minute=0, second=0, microsecond=0) - off
    end = start + timedelta(days=1)
    conn = None
    try:
        conn = connect(memory, config)
        rows = conn.execute(
            "SELECT id, payload, trigger_at FROM schedules "
            "WHERE kind='reminder' AND enabled=1 AND trigger_at IS NOT NULL "
            "ORDER BY trigger_at"
        ).fetchall()
        out = []
        for r in rows:
            t = parse_iso(r["trigger_at"])
            if t and start <= t < end:
                out.append({"id": r["id"], "text": json.loads(r["payload"]).get("text", ""),
                            "due_at": r["trigger_at"]})
        return out
    except Exception as e:
        log.warning(f"Reminder fetch failed: {type(e).__name__}")
        return []
    finally:
        if conn:
            conn.close()