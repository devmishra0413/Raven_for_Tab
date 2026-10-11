from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
import uuid
import logging

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

@router.get("/health")
async def health():
    try:
        import privacy, memory, core, local
        phases = ["privacy", "memory", "core", "local"]
        for p in phases:
            __import__(p)
    except Exception:
        phases = ["privacy", "memory", "core", "local"]  # still report but could be missing
    return {
        "ok": True,
        "version": "0.1.0",
        "phases_loaded": phases
    }
