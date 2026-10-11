"""ModelLifecycle: background load, idle/low-RAM unload, reload on message."""
from __future__ import annotations

import logging
import threading
import time
# imports


from .runner import get_local_cfg

log = logging.getLogger(__name__)


class ModelLifecycle:
    def __init__(self, runner, config: dict | None = None):
        cfg = get_local_cfg(config)
        self._runner = runner
        self._enabled = bool(cfg.get("enabled", True))
        self._idle_limit = float(cfg.get("idle_unload_minutes", 30)) * 60
        self._low_ram = int(cfg.get("low_ram_mb", 400))
        self._ram_poll = float(cfg.get("ram_poll_interval_seconds", 60))
        self._tick = float(cfg.get("monitor_tick_seconds", 5))
        self._cooldown = float(cfg.get("error_retry_seconds", 60))
        self._lock = threading.Lock()
        self._status = "unloaded"
        self._gen = 0
        self._mon_event = threading.Event()
        self._idle_start = time.monotonic()
        self._error_at = 0.0
        self._manual_off = False
        self._closed = False

    # ---- properties ----
    @property
    def status(self) -> str:
        return self._status

    @property
    def is_loaded(self) -> bool:
        return self._status == "ready"

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self._idle_start

    # ---- public API ----
    def start(self) -> None:
        """Startup: non-blocking background load (unless disabled)."""
        with self._lock:
            self._closed = False
            self._manual_off = False
            self._begin_load()

    def stop(self) -> None:
        """RAVEN quit."""
        with self._lock:
            self._closed = True
        self._unload("quit")

    def notify_message(self) -> None:
        """Every user message: reset idle; reload if unloaded/error."""
        with self._lock:
            self._idle_start = time.monotonic()
            if self._manual_off or self._closed:
                return
            if (self._status == "error"
                    and time.monotonic() - self._error_at < self._cooldown):
                return
            if self._ram_too_low():  # avoid reload->unload loop
                return
            self._begin_load()

    def notify_extraction_done(self) -> None:
        with self._lock:
            self._idle_start = time.monotonic()

    def load_now(self) -> None:
        """/model on (ignores error cooldown and manual-off)."""
        with self._lock:
            self._manual_off = False
            self._closed = False
            self._idle_start = time.monotonic()
            self._begin_load()

    def unload_now(self) -> None:
        """/model off (sticks until /model on)."""
        with self._lock:
            self._manual_off = True
        self._unload("manual")

    # ---- internals ----
    def _ram_too_low(self) -> bool:
        try:
            mb = self._runner.check_ram()
        except Exception:
            return False
        return mb != -1 and mb < self._low_ram

    def _begin_load(self) -> None:
        """Caller holds lock. Starts loader only if unloaded/error."""
        if not self._enabled or self._status not in ("unloaded", "error"):
            return
        self._status = "loading"
        self._gen += 1
        self._mon_event = threading.Event()
        threading.Thread(
            target=self._load_worker, args=(self._gen, self._mon_event),
            daemon=True,
        ).start()

    def _unload(self, reason: str) -> None:
        with self._lock:
            if self._status == "unloaded":
                return
            self._gen += 1  # invalidates loader/monitor
            ev = self._mon_event
            self._status = "unloaded"
        ev.set()
        try:
            self._runner.unload()
        except Exception as exc:
            log.warning("Unload failed (%s)", type(exc).__name__)
        log.info("Local model unloaded (%s)", reason)

    def _load_worker(self, gen: int, ev: threading.Event) -> None:
        try:
            self._runner.load()
        except Exception as exc:
            log.warning("Local model load failed (%s)", type(exc).__name__)
            with self._lock:
                if gen == self._gen:
                    self._status = "error"
                    self._error_at = time.monotonic()
            return
        with self._lock:
            stale = gen != self._gen or self._closed
            if not stale:
                self._status = "ready"
                self._idle_start = time.monotonic()
        if stale:
            try:
                self._runner.unload()
            except Exception:
                pass
            return
        self._monitor(gen, ev)

    def _monitor(self, gen: int, ev: threading.Event) -> None:
        """Idle check first, then low-RAM poll."""
        last_ram = 0.0
        while not ev.wait(self._tick):
            with self._lock:
                if gen != self._gen:
                    return
            if self.idle_seconds >= self._idle_limit:
                self._unload("idle")
                return
            now = time.monotonic()
            if now - last_ram >= self._ram_poll:
                last_ram = now
                if self._ram_too_low():
                    self._unload("low_ram")
                    return

    def __repr__(self) -> str:
        return f"<ModelLifecycle status={self._status}>"

    __str__ = __repr__