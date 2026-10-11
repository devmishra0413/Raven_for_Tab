"""
API routes for scheduler management.
"""

import logging
import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from privacy.pipeline import sanitize
from scheduler import build_briefing, generate_boot_script, install_boot_script, boot_status


log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scheduler")

# Global scheduler instance (set by main.py)
_scheduler = None


def set_scheduler(scheduler):
    """Set the global scheduler instance."""
    global _scheduler
    _scheduler = scheduler


class ReminderRequest(BaseModel):
    text: str
    due_at: str  # ISO8601 UTC


class TriggerRequest(BaseModel):
    condition: str
    action: str


class BootInstallRequest(BaseModel):
    project_path: str


@router.get("/jobs")
async def list_jobs():
    """
    List all enabled scheduled jobs.
    
    Returns job metadata without showing payload content.
    """
    if not _scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not running")
    
    import sqlite3
    
    conn = _scheduler._get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT id, kind, trigger_at, repeat_minutes, last_run_at, enabled, created_at
            FROM schedules
            WHERE enabled = 1
            ORDER BY created_at DESC
            """
        )
        
        jobs = []
        for row in cursor.fetchall():
            jobs.append({
                "id": row['id'],
                "kind": row['kind'],
                "trigger_at": row['trigger_at'],
                "repeat_minutes": row['repeat_minutes'],
                "last_run_at": row['last_run_at'],
                "enabled": bool(row['enabled']),
                "created_at": row['created_at']
            })
        
        return JSONResponse(status_code=200, content={"jobs": jobs})
    finally:
        conn.close()


@router.post("/reminder")
async def create_reminder(req: ReminderRequest):
    if not _scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not running")

    try:
        due = datetime.fromisoformat(req.due_at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid due_at (expected ISO8601 UTC)")
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    due_iso = due.astimezone(timezone.utc).isoformat()

    from privacy import sanitize
    from api.routes.chat import get_session
    sess = get_session()
    try:
        entities = sess.manager.entity_list()
    except Exception:
        entities = []
    guard = sanitize(req.text, entities=entities, vault=sess.vault)
    if guard.blocked or guard.needs_permission:
        return JSONResponse(status_code=400,
                            content={"error": "Reminder text blocked by privacy filter"})

    job_id = _scheduler.add_reminder(guard.clean_text[:200], due_iso)
    return JSONResponse(status_code=200, content={"job_id": job_id})

@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: int):
    """Cancel a scheduled job."""
    if not _scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not running")
    
    _scheduler.cancel_job(job_id)
    return JSONResponse(status_code=200, content={"ok": True})


@router.get("/briefing/preview")
async def briefing_preview():
    """
    Generate and return briefing content without sending notification.
    """
    if not _scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not running")
    
    content = build_briefing(_scheduler.memory, _scheduler.config)
    return JSONResponse(status_code=200, content={"content": content})


@router.post("/briefing/send")
async def briefing_send():
    """
    Generate and send briefing notification now.
    """
    if not _scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not running")
    
    from scheduler.jobs import run_briefing
    
    payload = {"scheduled_time": "manual"}
    run_briefing(payload, _scheduler.memory, _scheduler.config)
    
    return JSONResponse(status_code=200, content={"ok": True})


@router.get("/boot")
async def get_boot_status():
    """Check if Termux:Boot script is installed."""
    status = boot_status()
    return JSONResponse(status_code=200, content=status)


@router.post("/boot/install")
async def install_boot(req: BootInstallRequest):
    """
    Install Termux:Boot startup script.
    """
    success = install_boot_script(req.project_path)
    
    if success:
        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "message": "Boot script installed successfully"
            }
        )
    else:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "message": "Termux:Boot directory not found. Install Termux:Boot from F-Droid first."
            }
        )


@router.get("/triggers")
async def list_triggers():
    """List all enabled trigger jobs."""
    if not _scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not running")
    
    import sqlite3
    
    conn = _scheduler._get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT id, payload, created_at
            FROM schedules
            WHERE kind = 'trigger' AND enabled = 1
            ORDER BY created_at DESC
            """
        )
        
        triggers = []
        for row in cursor.fetchall():
            payload = json.loads(row['payload'])
            triggers.append({
                "id": row['id'],
                "condition": payload.get("condition", ""),
                "action": payload.get("action", ""),
                "created_at": row['created_at']
            })
        
        return JSONResponse(status_code=200, content={"triggers": triggers})
    finally:
        conn.close()


@router.post("/triggers")
async def create_trigger(req: TriggerRequest):
    """
    Create a new trigger rule.
    
    Validates condition and action against allowed lists.
    """
    if not _scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not running")
    
    from scheduler.triggers import ALLOWED_CONDITIONS, ALLOWED_ACTIONS
    
    # Validate condition
    if req.condition not in ALLOWED_CONDITIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid condition. Allowed: {list(ALLOWED_CONDITIONS.keys())}"
        )
    
    # Validate action
    if req.action not in ALLOWED_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action. Allowed: {list(ALLOWED_ACTIONS.keys())}"
        )
    
    # Create trigger job
    payload = {
        "condition": req.condition,
        "action": req.action
    }
    
    conn = _scheduler._get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO schedules (kind, trigger_at, repeat_minutes, payload, enabled)
            VALUES (?, NULL, NULL, ?, 1)
            """,
            ("trigger", json.dumps(payload))
        )
        conn.commit()
        job_id = cursor.lastrowid
        
        return JSONResponse(
            status_code=201,
            content={"job_id": job_id}
        )
    finally:
        conn.close()


@router.delete("/triggers/{trigger_id}")
async def delete_trigger(trigger_id: int):
    """Delete a trigger rule."""
    if not _scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not running")
    
    _scheduler.cancel_job(trigger_id)
    return JSONResponse(status_code=200, content={"ok": True})
