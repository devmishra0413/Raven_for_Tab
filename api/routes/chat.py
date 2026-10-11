import hashlib
import json
import logging
import os
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.store import PendingMessage, PendingStore, create_pending_message
from core.session import Session
from memory import build_cloud_context
from privacy import GuardResult, Vault, sanitize

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat")

# Shared singletons/accessors
_pending_store = PendingStore()
_session: Optional[Session] = None
_cloud_client: Any = None


def get_pending_store() -> PendingStore:
    return _pending_store


def set_pending_store(store: PendingStore) -> None:
    global _pending_store
    _pending_store = store


def get_session() -> Session:
    global _session
    if _session is None:
        cfg_path = os.path.join(os.path.dirname(__file__), "../../config.json")
        config = {"session": {"history_messages": 6}}
        db_path = "data/raven.db"
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    config = cfg
                    db_path = cfg.get("paths", {}).get("db", "data/raven.db")
            except Exception:
                pass
        _session = Session(config, db_path=db_path)
    return _session


def set_session(session_instance: Session) -> None:
    global _session
    _session = session_instance


def get_cloud_client() -> Any:
    global _cloud_client
    return _cloud_client


def set_cloud_client(client: Any) -> None:
    global _cloud_client
    _cloud_client = client


def _get_system_prompt() -> str:
    cfg_path = os.path.join(os.path.dirname(__file__), "../../config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return cfg.get("system_prompt", "You are RAVEN, a privacy-first personal assistant.")
        except Exception:
            pass
    return "You are RAVEN, a privacy-first personal assistant."


@router.post("/message")
async def chat_message(req: dict):
    if not isinstance(req, dict):
        return JSONResponse(status_code=400, content={"error": "Invalid request body", "code": "INVALID_INPUT"})
    text = req.get("text")
    if not isinstance(text, str) or not text.strip():
        return JSONResponse(status_code=400, content={"error": "Empty text", "code": "INVALID_INPUT"})
    if len(text) > 2000:
        return JSONResponse(status_code=400, content={"error": "Text exceeds 2000 characters", "code": "INVALID_INPUT"})

    sess = get_session()
    store = get_pending_store()
    
    try:
        entities = sess.manager.entity_list()
    except Exception:
        entities = []

    guard = sanitize(text, entities=entities, vault=sess.vault)

    if guard.blocked:
        msg_id = str(uuid.uuid4())
        msg = PendingMessage(
            message_id=msg_id,
            clean_text="",
            payload={},
            payload_hash="",
            vault=sess.vault,
            status="blocked",
            created_at=time.time(),
            needs_permission=False,
        )
        store.put(msg)
        return JSONResponse(status_code=200, content={
            "message_id": msg_id,
            "status": "blocked",
            "reason": guard.reason or "blocked",
        })

    if guard.needs_permission:
        msg_id = str(uuid.uuid4())
        try:
            context_facts = build_cloud_context(sess.manager, text, vault=sess.vault)
        except Exception:
            context_facts = []
        recent = sess.history_messages()[-6:]
        messages = [{"role": "system", "content": _get_system_prompt()}]
        if context_facts:
            messages.append({"role": "system", "content": "Relevant facts:\n" + "\n".join(f"- {f}" for f in context_facts)})
        for m in recent:
            messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})
        messages.append({"role": "user", "content": guard.clean_text})
        payload = {"messages": messages}
        payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

        msg = PendingMessage(
            message_id=msg_id,
            clean_text=guard.clean_text,
            payload=payload,
            payload_hash=payload_hash,
            vault=sess.vault,
            status="needs_permission",
            created_at=time.time(),
            needs_permission=True,
        )
        store.put(msg)
        topic_label = guard.reason or "unknown"
        if topic_label.startswith("topic:"):
            topic_label = topic_label.split(":", 1)[1]
        return JSONResponse(status_code=200, content={
            "message_id": msg_id,
            "status": "needs_permission",
            "topic": topic_label,
        })

    # Normal preview
    try:
        context_facts = build_cloud_context(sess.manager, text, vault=sess.vault)
    except Exception:
        context_facts = []
    recent = sess.history_messages()[-6:]
    messages = [{"role": "system", "content": _get_system_prompt()}]
    if context_facts:
        messages.append({"role": "system", "content": "Relevant facts:\n" + "\n".join(f"- {f}" for f in context_facts)})
    for m in recent:
        messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})
    messages.append({"role": "user", "content": guard.clean_text})
    payload = {"messages": messages}

    pending = create_pending_message(
        clean_text=guard.clean_text,
        payload=payload,
        vault=sess.vault,
        status="preview",
        needs_permission=False,
    )
    store.put(pending)

    return JSONResponse(status_code=200, content={
        "message_id": pending.message_id,
        "status": "preview",
        "preview": {
            "payload": payload["messages"],
            "hash": pending.payload_hash,
            "masked_count": len(recent),
            "context_facts": len(context_facts),
        },
    })


@router.post("/send")
async def chat_send(req: dict):
    if not isinstance(req, dict):
        return JSONResponse(status_code=400, content={"error": "Invalid request body", "code": "INVALID_INPUT"})
    message_id = req.get("message_id")
    provided_hash = req.get("hash")

    if not message_id or not provided_hash:
        return JSONResponse(status_code=400, content={"error": "Missing message_id or hash", "code": "INVALID_INPUT"})

    store = get_pending_store()
    msg = store.get(message_id)

    if msg is None:
        return JSONResponse(status_code=404, content={"error": "Message not found or expired", "code": "NOT_FOUND"})

    if msg.status in ("sent", "cancelled", "blocked", "needs_permission"):
        return JSONResponse(status_code=400, content={"error": f"Message cannot be sent (status: {msg.status})", "code": "INVALID_STATE"})

    # Hash verification
    expected_hash = hashlib.sha256(json.dumps(msg.payload, sort_keys=True).encode("utf-8")).hexdigest()
    if provided_hash != msg.payload_hash or provided_hash != expected_hash:
        return JSONResponse(status_code=400, content={"error": "Payload hash mismatch", "code": "HASH_MISMATCH"})

    # Mark sent atomically BEFORE cloud call
    msg.status = "sent"

    client = get_cloud_client()
    if client is None:
        return JSONResponse(status_code=500, content={"error": "Cloud client not configured", "code": "CLOUD_ERROR"})

    try:
        chat_result = client.chat(msg.payload)
    except Exception as exc:
        log.error("Cloud call failed: %s", type(exc).__name__)
        return JSONResponse(status_code=502, content={"error": "Cloud request failed", "code": "CLOUD_ERROR"})

    reply_masked = chat_result.content if hasattr(chat_result, "content") else str(chat_result)
    reply_unmasked = msg.vault.unmask(reply_masked) if hasattr(msg.vault, "unmask") else reply_masked

    sess = get_session()
    sess.add_exchange(msg.clean_text, reply_masked)
    if req.get("speak"):
        try:
            from api.routes.voice import get_voice_pipeline
            import threading
            vp = get_voice_pipeline()
            if vp:
                threading.Thread(target=vp.speak_text, args=(reply_unmasked,),
                                 daemon=True).start()
        except Exception:
            pass   

    return JSONResponse(status_code=200, content={
        "message_id": msg.message_id,
        "status": "sent",
        "reply": reply_masked,
        "reply_unmasked": reply_unmasked,
    })


@router.post("/cancel")
async def chat_cancel(req: dict):
    if not isinstance(req, dict):
        return JSONResponse(status_code=400, content={"error": "Invalid request body", "code": "INVALID_INPUT"})
    message_id = req.get("message_id")
    if not message_id:
        return JSONResponse(status_code=400, content={"error": "Missing message_id", "code": "INVALID_INPUT"})

    store = get_pending_store()
    msg = store.get(message_id)

    if msg is None:
        return JSONResponse(status_code=404, content={"error": "Message not found or expired", "code": "NOT_FOUND"})

    msg.status = "cancelled"
    store.delete(message_id)

    return JSONResponse(status_code=200, content={
        "message_id": message_id,
        "status": "cancelled",
    })


@router.post("/permit")
async def chat_permit(req: dict):
    if not isinstance(req, dict):
        return JSONResponse(status_code=400, content={"error": "Invalid request body", "code": "INVALID_INPUT"})
    message_id = req.get("message_id")
    allow = req.get("allow")

    if not message_id or not isinstance(allow, bool):
        return JSONResponse(status_code=400, content={"error": "Missing message_id or allow boolean", "code": "INVALID_INPUT"})

    store = get_pending_store()
    msg = store.get(message_id)

    if msg is None:
        return JSONResponse(status_code=404, content={"error": "Message not found or expired", "code": "NOT_FOUND"})

    if msg.status != "needs_permission":
        return JSONResponse(status_code=400, content={"error": "Message does not require permission", "code": "INVALID_STATE"})

    if not allow:
        msg.status = "cancelled"
        store.delete(message_id)
        return JSONResponse(status_code=200, content={
            "message_id": message_id,
            "status": "cancelled",
        })

    msg.status = "preview"
    msg.needs_permission = False
    sess = get_session()

    messages = msg.payload.get("messages", []) if isinstance(msg.payload, dict) else []

    return JSONResponse(status_code=200, content={
        "message_id": msg.message_id,
        "status": "preview",
        "preview": {
            "payload": messages,
            "hash": msg.payload_hash,
            "masked_count": len(sess.history_messages()[-6:]),
            "context_facts": 0,
        },
    })


@router.get("/history")
async def chat_history():
    sess = get_session()
    return JSONResponse(status_code=200, content={
        "history": sess.history_messages(),
    })
