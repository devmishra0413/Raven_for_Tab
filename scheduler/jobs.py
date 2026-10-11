"""Job execution. No shell, no payload logging."""
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)
_WS = Path.home() / "raven_workspace"


def termux_api_available() -> bool:
    return shutil.which("termux-notification") is not None


def _safe_text(text: str) -> str:
    """Last-line sanitize for generated notification text (fresh vault)."""
    try:
        from privacy import sanitize
        g = sanitize(text)
        text = "RAVEN: open the app for details" if g.blocked else g.clean_text
    except Exception:
        pass
    return text[:200]


def _write(name: str, text: str, append: bool = False) -> None:
    _WS.mkdir(exist_ok=True)
    with open(_WS / name, "a" if append else "w", encoding="utf-8") as f:
        if append:
            f.write(f"{datetime.now(timezone.utc).isoformat()}: {text}\n")
        else:
            f.write(text)


def _notify(title: str, text: str, nid=None) -> bool:
    if not termux_api_available():
        return False
    cmd = ["termux-notification", "--title", title, "--content", text]
    if nid is not None:
        cmd += ["--id", str(nid)]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=5).returncode == 0
    except Exception as e:
        log.warning(f"Notification failed: {type(e).__name__}")
        return False


def run_reminder(payload: dict) -> None:
    text = str(payload.get("text", ""))[:200]  # sanitized at creation; not re-sanitized
    if not _notify("RAVEN Reminder", text, payload.get("original_job_id", 0)):
        _write("reminders_fired.txt", text, append=True)


def run_briefing(payload: dict, memory, config: dict) -> None:
    from scheduler.briefing import build_briefing
    content = build_briefing(memory, config)
    _write("briefing_latest.txt", content)
    if not _notify("RAVEN Daily Briefing", _safe_text(content)):
        log.info("Briefing saved to file (notification unavailable)")


def run_trigger(payload: dict, memory, config: dict) -> None:
    from scheduler.triggers import TriggerEngine
    eng = TriggerEngine(memory, config)
    if eng.check_condition(payload.get("condition", "")):
        eng.execute_action(payload.get("action", ""))