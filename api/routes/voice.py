"""
API routes for voice interaction.
"""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from voice import VoicePipeline

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/voice")

# Global voice pipeline instance (set by main.py)
_voice_pipeline: Optional[VoicePipeline] = None


def set_voice_pipeline(pipeline: VoicePipeline) -> None:
    """Set the global voice pipeline instance."""
    global _voice_pipeline
    _voice_pipeline = pipeline


def get_voice_pipeline() -> Optional[VoicePipeline]:
    """Get the global voice pipeline instance."""
    return _voice_pipeline


class SpeakRequest(BaseModel):
    text: str


class ConfigUpdateRequest(BaseModel):
    wake_word_enabled: Optional[bool] = None
    tts_speed: Optional[float] = None
    stt_language: Optional[str] = None


@router.get("/status")
async def voice_status():
    p = _voice_pipeline
    stt_ok = bool(shutil.which(p.stt.binary)) and Path(p.stt.model_path).exists()
    tts_ok = bool(shutil.which(p.tts.binary)) and Path(p.tts.model_path).exists()
    return JSONResponse(status_code=200, content={
        "wake_word": p.wake_word.status if p.wake_word else "stopped",
        "stt_available": stt_ok,
        "tts_available": tts_ok,
        "mic_permission": check_mic_permission(),
    })


@router.post("/mic")
async def voice_mic():
    """Trigger mic button recording."""
    if not _voice_pipeline:
        raise HTTPException(status_code=503, detail="Voice pipeline not running")
    
    job_id = _voice_pipeline.trigger_mic_button()
    return JSONResponse(status_code=200, content={"job_id": job_id})


@router.get("/result/{job_id}")
async def voice_result(job_id: str):
    """Get mic button job result."""
    if not _voice_pipeline:
        raise HTTPException(status_code=503, detail="Voice pipeline not running")
    
    result = _voice_pipeline.get_mic_result(job_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    
    return JSONResponse(
        status_code=200,
        content={
            "status": result["status"],
            "text": result["text"],
            "reply": result["reply"],
            "error": result["error"]
        }
    )


@router.post("/speak")
async def voice_speak(req: SpeakRequest):
    """Speak text via TTS."""
    if not _voice_pipeline:
        raise HTTPException(status_code=503, detail="Voice pipeline not running")
    
    # Max 500 chars
    text = req.text[:500]
    
    success = _voice_pipeline.speak_text(text)
    
    if success:
        return JSONResponse(status_code=200, content={"ok": True})
    else:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "TTS failed"}
        )


@router.get("/config")
async def voice_config_get():
    """Get voice configuration (safe values only)."""
    if not _voice_pipeline:
        return JSONResponse(
            status_code=200,
            content={
                "enabled": False,
                "wake_word_enabled": False,
                "stt_language": "auto",
                "tts_speed": 1.0
            }
        )
    
    config = _voice_pipeline.config
    wake_config = config.get("wake_word", {})
    stt_config = config.get("stt", {})
    tts_config = config.get("tts", {})
    
    return JSONResponse(
        status_code=200,
        content={
            "enabled": config.get("enabled", True),
            "wake_word_enabled": wake_config.get("enabled", False),
            "stt_language": stt_config.get("language", "auto"),
            "tts_speed": tts_config.get("speed", 1.0)
        }
    )


@router.patch("/config")
async def voice_config_update(req: ConfigUpdateRequest):
    """Update voice configuration (runtime only)."""
    if not _voice_pipeline:
        raise HTTPException(status_code=503, detail="Voice pipeline not running")
    
    config = _voice_pipeline.config.get("voice", {})
    
    if req.wake_word_enabled is not None:
        config.setdefault("wake_word", {})["enabled"] = req.wake_word_enabled
        if req.wake_word_enabled:
            _voice_pipeline.wake_word.start(_voice_pipeline.handle_wake_word)
        else:
            _voice_pipeline.wake_word.stop()
    
    if req.tts_speed is not None:
        v = max(0.5, min(2.0, req.tts_speed))
        config.setdefault("tts", {})["speed"] = v
        _voice_pipeline.tts.speed = v
    if req.stt_language is not None:
        config.setdefault("stt", {})["language"] = req.stt_language
        _voice_pipeline.stt.language = req.stt_language
    return JSONResponse(status_code=200, content={"ok": True})