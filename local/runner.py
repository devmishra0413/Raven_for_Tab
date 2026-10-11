"""LocalRunner: subprocess wrapper for a llama.cpp CLI. Stdlib only."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from .exceptions import (
    ModelCallError,
    ModelLoadError,
    ModelNotReadyError,
    ModelTimeoutError,
)

log = logging.getLogger(__name__)
_warned_no_meminfo = False


def get_local_cfg(config: dict | None) -> dict:
    """Accept full config.json or just its 'local_model' section."""
    config = config or {}
    sec = config.get("local_model")
    return dict(sec) if isinstance(sec, dict) else dict(config)


class LocalRunner:
    def __init__(self, config: dict, project_root: str | os.PathLike | None = None):
        cfg = get_local_cfg(config)
        self._root = Path(project_root) if project_root else Path.cwd()
        self._binary_cfg = str(cfg.get("binary", "") or "")
        self._model_cfg = str(cfg.get("model_path", "") or "")
        self._n_ctx = int(cfg.get("n_ctx", 1024))
        self._threads = int(cfg.get("threads", 4))
        self._max_tokens = int(cfg.get("max_tokens", 256))
        self._timeout = float(cfg.get("timeout_seconds", 45))
        self._extra_args = [str(a) for a in cfg.get("extra_args", [])]
        self._binary: str | None = None
        self._model: Path | None = None
        self._status = "unloaded"
        self._lock = threading.Lock()        # guards status/_proc
        self._call_lock = threading.Lock()   # one inference at a time
        self._proc: subprocess.Popen | None = None

    # ---- status ----
    @property
    def status(self) -> str:
        return self._status

    def is_ready(self) -> bool:
        return self._status == "ready"

    # ---- load / unload ----
    def _resolve_model(self) -> Path:
        raw = os.environ.get("RAVEN_MODEL_PATH") or self._model_cfg
        if not raw:
            raise ModelLoadError("Model path not configured")
        p = Path(raw)
        return p if p.is_absolute() else (self._root / p)

    def _resolve_binary(self) -> str:
        if not self._binary_cfg:
            raise ModelLoadError("Binary not configured")
        b = Path(self._binary_cfg)
        if b.parent != Path("."):  # has a directory part -> path
            cand = b if b.is_absolute() else self._root / b
            if cand.is_file() and os.access(cand, os.X_OK):
                return str(cand)
            raise ModelLoadError("Binary not found or not executable")
        found = shutil.which(self._binary_cfg)
        if not found:
            raise ModelLoadError("Binary not found")
        return found

    def load(self) -> None:
        """Verify binary + model exist. Raises ModelLoadError (generic msg)."""
        try:
            binary = self._resolve_binary()
            model = self._resolve_model()
            if not model.is_file():
                raise ModelLoadError("Model file not found")
        except ModelLoadError:
            with self._lock:
                self._status = "error"
            raise
        with self._lock:
            self._binary, self._model = binary, model
            self._status = "ready"

    def unload(self) -> None:
        """Kill any running call and mark unloaded."""
        with self._lock:
            self._status = "unloaded"
            proc = self._proc
        self._kill(proc)

    @staticmethod
    def _kill(proc: subprocess.Popen | None) -> None:
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

    # ---- inference ----
    def call(self, prompt: str) -> str:
        if not self.is_ready():
            raise ModelNotReadyError("Model not ready")
        with self._call_lock:
            if not self.is_ready():
                raise ModelNotReadyError("Model not ready")
            fd, tmp = tempfile.mkstemp(prefix="rvn_", suffix=".txt")  # mode 0600
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(prompt)
                args = [
                    self._binary, "-m", str(self._model), "-f", tmp,
                    "-n", str(self._max_tokens), "-c", str(self._n_ctx),
                    "-t", str(self._threads),
                    "-no-cnv", "--no-display-prompt", "--log-disable",
                    *self._extra_args,
                ]
                return self._run(args)
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def _run(self, args: list[str]) -> str:
        try:
            proc = subprocess.Popen(
                args, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace",
            )
        except OSError as exc:
            self._set_error()
            raise ModelLoadError("Could not start binary") from exc
        with self._lock:
            self._proc = proc
        try:
            try:
                out, _ = proc.communicate(timeout=self._timeout)
            except subprocess.TimeoutExpired:
                self._kill(proc)
                try:
                    proc.communicate(timeout=5)
                except Exception:
                    pass
                self._set_error()
                raise ModelTimeoutError("Model call timed out") from None
            if self._status == "unloaded":  # unloaded during the call
                raise ModelNotReadyError("Model unloaded during call")
            if proc.returncode != 0:
                self._set_error()
                raise ModelCallError("Model process failed")
            return out or ""
        finally:
            with self._lock:
                self._proc = None

    def _set_error(self) -> None:
        with self._lock:
            if self._status != "unloaded":
                self._status = "error"

    # ---- RAM ----
    def check_ram(self) -> int:
        """MemAvailable in MB, or -1 if unavailable (warns once)."""
        global _warned_no_meminfo
        try:
            with open("/proc/meminfo", encoding="ascii") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) // 1024
        except (OSError, ValueError, IndexError):
            pass
        if not _warned_no_meminfo:
            _warned_no_meminfo = True
            log.warning("/proc/meminfo unavailable; RAM check disabled")
        return -1

    # ---- repr: no paths ----
    def __repr__(self) -> str:
        return f"<LocalRunner status={self._status}>"

    __str__ = __repr__