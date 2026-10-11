import logging
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi import BackgroundTasks
from fastapi.responses import PlainTextResponse
from uuid import uuid4
from typing import Callable, Awaitable
import copy
scheduler_instance = None
voice_instance = None

app = FastAPI(
    title="RAVEN API",
    description="Privacy-first Personal AI Assistant API",
    version="0.1.0",
)

log = logging.getLogger(__name__)


# ============================================================
# API ROUTER REGISTRATION
# ============================================================

from api.routes import chat, health, scheduler, tools, voice

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(scheduler.router)
app.include_router(tools.router)
app.include_router(voice.router)

log.info("RAVEN API routers registered")


# ============================================================
# 1. SECURITY HEADERS
# ============================================================

@app.middleware("http")
async def security_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:

    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"

    return response


# ============================================================
# 2. REQUEST ID
# ============================================================

@app.middleware("http")
async def request_id(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:

    rid = str(uuid4())

    response = await call_next(request)

    response.headers["X-Request-ID"] = rid

    log.info(
        "%s %s -> %s [%s]",
        request.method,
        request.url.path,
        response.status_code,
        rid,
    )

    return response


# ============================================================
# 3. LOCALHOST ENFORCEMENT
# ============================================================

@app.middleware("http")
async def enforce_localhost(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:

    host = request.headers.get("host", "").split(":")[0]

    if host not in ("127.0.0.1", "localhost"):
        return PlainTextResponse(
            "Forbidden",
            status_code=403,
        )

    return await call_next(request)


# ============================================================
# VOICE INITIALIZATION
# ============================================================

def _start_voice(cfg) -> None:
    global voice_instance

    vcfg = copy.deepcopy(cfg.get("voice", {}))

    if not vcfg.get("enabled"):
        log.info("Voice pipeline disabled in configuration")
        return

    # CLI owns the wake-word microphone.
    vcfg.setdefault("wake_word", {})["enabled"] = False

    from core.audit import AuditLogger
    from core.config import get_api_key
    from core.orchestrator import Orchestrator

    from api.routes.chat import get_session
    from api.routes.voice import set_voice_pipeline

    from llm.cloud_client import OpenRouterClient
    from llm.transport import UrlLibTransport

    from voice.pipeline import VoicePipeline
    from voice.wake_word import WakeWordDetector
    from voice.stt import WhisperSTT
    from voice.tts import PiperTTS

    client = OpenRouterClient(
        UrlLibTransport(
            base_url=cfg["cloud"]["base_url"],
            api_key=get_api_key(cfg),
            timeout=cfg["cloud"]["timeout_seconds"],
        ),
        cfg,
    )

    orch = Orchestrator(
        get_session(),
        cfg,
        AuditLogger(cfg.db_path),
        ask_permission=lambda r: False,
        confirm_send=lambda p, m: True,
    )

    voice_instance = VoicePipeline(
        wake_word=WakeWordDetector(vcfg["wake_word"]),
        stt=WhisperSTT(vcfg.get("stt", {})),
        tts=PiperTTS(vcfg.get("tts", {})),
        config=vcfg,
        on_text_ready=lambda t: orch.run(t).text,
    )

    voice_instance.start()

    set_voice_pipeline(voice_instance)

    log.info("Voice pipeline started")


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
async def startup():
    global scheduler_instance

    log.info("RAVEN server starting")

    # Load configuration.
    try:
        from core.config import Config
        from api.routes.chat import get_session

        cfg = Config.load("config.json")

    except Exception:
        log.exception("Configuration loading failed")
        return

    # Initialize scheduler if enabled.
    try:
        scfg = dict(cfg.get("scheduler", {}))

        if scfg.get("enabled"):
            from scheduler.engine import SchedulerEngine
            from api.routes.scheduler import set_scheduler

            scfg["db_path"] = cfg.db_path

            scheduler_instance = SchedulerEngine(
                get_session().manager,
                scfg,
            )

            scheduler_instance.start()

            set_scheduler(scheduler_instance)

            log.info("Scheduler started")

        else:
            log.info("Scheduler disabled in configuration")

    except Exception:
        log.exception("Scheduler initialization failed")

    # Initialize voice pipeline if enabled.
    try:
        _start_voice(cfg)

    except Exception:
        log.exception("Voice initialization failed")


# ============================================================
# SHUTDOWN
# ============================================================

@app.on_event("shutdown")
async def shutdown():
    global scheduler_instance, voice_instance

    if voice_instance:
        try:
            voice_instance.stop()
            log.info("Voice pipeline stopped")

        except Exception:
            log.exception("Voice pipeline shutdown failed")

        finally:
            voice_instance = None

    if scheduler_instance:
        try:
            scheduler_instance.stop()
            log.info("Scheduler stopped")

        except Exception:
            log.exception("Scheduler shutdown failed")

        finally:
            scheduler_instance = None


# ============================================================
# ROOT ENDPOINT
# ============================================================
# ============================================================
# FRONTEND
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
INDEX_FILE = BASE_DIR / "ui" / "dist" / "index.html"


@app.get("/", include_in_schema=False)
async def serve_frontend():
    if not INDEX_FILE.is_file():
        return {
            "error": "Frontend index.html not found",
            "expected_path": str(INDEX_FILE),
        }

    return FileResponse(
        path=INDEX_FILE,
        media_type="text/html",
    )