"""Phase 3 CLI: plain terminal chat loop with slash commands.

Memory commands show RAW data on YOUR terminal (it never leaves the device).
Chat messages go through the Orchestrator (sanitize -> preview -> cloud).
Voice pipeline available via --voice-check flag.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any

from core.audit import AuditLogger
from core.config import ALLOWED_PREVIEWS, Config, get_api_key
from core.errors import AuditError, CloudError, ConfigError, RavenError
from core.orchestrator import Orchestrator
from core.session import Session
from llm.cloud_client import OpenRouterClient
from llm.transport import UrlLibTransport
from memory.exceptions import MemoryError_

HELP = """Commands:
  /new                      clear session (vault + history)
  /remember <text>          save a fact to memory
  /memory                   list saved facts
  /forget <id>              delete a fact
  /search <query>           search memory
  /preview always|when_masked|never   (this session only)
  /models                   show model order
  /audit                    last 10 audit entries (sanitized)
  /help                     this help
  /quit                     exit"""


class _NoKeyClient:
    """Used when the API key env var is missing: chat fails clearly, memory still works."""

    def __init__(self, message: str) -> None:
        self._message = message

    def chat(self, payload: dict) -> Any:
        raise CloudError(self._message)


def _fmt_fact(f: Any) -> str:
    return f"[{f.id}] ({f.category}, s={f.sensitivity}, {f.status}) {f.content}"


def _command(line: str, orch: Orchestrator, session: Session, audit: AuditLogger) -> bool:
    """Run one slash command. Returns False to quit."""
    cmd, _, arg = line[1:].partition(" ")
    cmd, arg = cmd.lower(), arg.strip()
    mem = session.manager

    if cmd in ("quit", "exit", "q"):
        return False
    if cmd == "help":
        print(HELP)
    elif cmd == "new":
        session.clear()
        print("Session cleared (vault + history).")
    elif cmd == "remember":
        if not arg:
            print("Usage: /remember <text>")
        else:
            f = mem.add(arg)
            note = "  (private: never sent to cloud)" if f.sensitivity else ""
            print(f"Saved: id={f.id} category={f.category} sensitivity={f.sensitivity}{note}")
    elif cmd == "memory":
        facts = mem.list(limit=50)
        print("\n".join(_fmt_fact(f) for f in facts) if facts else "No facts saved.")
    elif cmd == "forget":
        if not arg.isdigit():
            print("Usage: /forget <id>")
        else:
            mem.delete(int(arg))
            print(f"Deleted: id={arg}")
    elif cmd == "search":
        if not arg:
            print("Usage: /search <query>")
        else:
            facts = mem.search(arg, k=5, include_sensitive=True)
            print("\n".join(_fmt_fact(f) for f in facts) if facts else "No results.")
    elif cmd == "preview":
        if arg not in ALLOWED_PREVIEWS:
            print(f"Current: {orch.preview_mode}. Usage: /preview " + "|".join(ALLOWED_PREVIEWS))
        else:
            orch.preview_mode = arg
            print(f"Preview mode: {arg} (this session only)")
    elif cmd == "models":
        for i, m in enumerate(orch.models, 1):
            print(f"  {i}. {m}")
    elif cmd == "audit":
        rows = audit.recent(10)
        if not rows:
            print("Audit log is empty.")
        for r in rows:
            print(f"  {r['ts']}  {r['kind']:<10} {(r['status'] or '-'):<24} "
                  f"{r['model'] or '-'}  {(r['payload_hash'] or '')[:8]}")
    else:
        print(f"Unknown command: /{cmd}. Type /help.")
    return True


def main() -> int:
    # Parse arguments
    parser = argparse.ArgumentParser(description="RAVEN - Privacy-first personal assistant")
    parser.add_argument("--voice-check", action="store_true", help="Run voice component checks and exit")
    args = parser.parse_args()
    
    try:
        config = Config.load("config.json")
    except ConfigError as exc:
        print(f"Config error: {exc}")
        return 1

    # Voice check mode
    if args.voice_check:
        try:
            from voice.pipeline import run_voice_check
            run_voice_check(config)
            return 0
        except Exception as exc:
            print(f"Voice check failed: {exc}")
            return 1

    try:
        key = get_api_key(config)
        client: Any = OpenRouterClient(
            UrlLibTransport(
                base_url=config["cloud"]["base_url"],
                api_key=key,
                timeout=config["cloud"]["timeout_seconds"],
            ),
            config,
        )
    except ConfigError as exc:
        print(f"Warning: {exc}\nChat is disabled; memory commands still work.")
        client = _NoKeyClient("API key not set. Check the environment variable.")

    try:
        audit = AuditLogger(config.db_path)
        session = Session(config, config.db_path)
    except (RavenError, MemoryError_) as exc:
        print(f"Startup error: {exc}")
        return 1

    # Phase 7: Start scheduler if enabled
    orch = Orchestrator(session, config, audit, client)
    voice_orch = Orchestrator(
        session, config, audit, client,
        ask_permission=lambda reason: False,
        confirm_send=lambda payload, models: True,
    )
    chat_lock = threading.Lock()  # one chat at a time (typed + voice)

    scheduler = None
    scfg = dict(config.get("scheduler", {}))
    if scfg.get("enabled", False):
        try:
            from scheduler.engine import SchedulerEngine
            scfg["db_path"] = config.db_path
            scheduler = SchedulerEngine(session.manager, scfg)
            scheduler.start()
            print("Scheduler started")
        except Exception as exc:
            print(f"Warning: Scheduler failed to start: {type(exc).__name__}")

    voice_pipeline = None
    vcfg = config.get("voice", {})
    if vcfg.get("enabled", False):
        try:
            from voice.pipeline import VoicePipeline
            from voice.wake_word import WakeWordDetector
            from voice.stt import WhisperSTT
            from voice.tts import PiperTTS

            def on_text_ready(text: str) -> str:
                with chat_lock:
                    reply = orch.run(text)  # sanitize happens inside orch.run
                return reply.text if reply.status == "ok" else ""

            wcfg = dict(vcfg.get("wake_word", {}))
            wcfg["sample_rate"] = vcfg.get("audio", {}).get("sample_rate", 16000)
            voice_pipeline = VoicePipeline(
                wake_word=WakeWordDetector(wcfg),
                stt=WhisperSTT(vcfg.get("stt", {})),
                tts=PiperTTS(vcfg.get("tts", {})),
                config=vcfg,
                on_text_ready=on_text_ready,
            )
            voice_pipeline.start()
            print("Voice pipeline started")
        except Exception as exc:
            print(f"Warning: Voice pipeline failed: {type(exc).__name__}")

    print("RAVEN ready. Type /help for commands.")
    try:
        while True:
            try:
                line = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            if line.startswith("/"):
                try:
                    if not _command(line, orch, session, audit):
                        break
                except (MemoryError_, AuditError) as exc:
                    print(f"Error: {exc}")
                except Exception:
                    print("Command failed.")
                continue
            with chat_lock:
                reply = orch.run(line)
            if reply.status == "ok":
                print(f"\nRAVEN: {reply.text}")
                if reply.model:
                    print(f"[model: {reply.model}]")
            else:
                print(f"\n[{reply.status}] {reply.text}")
    finally:
        if voice_pipeline:
            voice_pipeline.stop()
        if scheduler:
            scheduler.stop()
        orch.close()
        print("Session cleared. Bye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())