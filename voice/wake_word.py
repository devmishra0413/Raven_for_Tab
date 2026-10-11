"""Wake word (openWakeWord). BEST EFFORT on Termux: see VOICE_NOTES.md.

termux-microphone-record cannot stream, so we record short windows, feed them
to the model in 80 ms frames, and discard anything recorded while paused.
"""
import logging
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)
_FRAME = 1280  # 80 ms @ 16 kHz, what openWakeWord expects


class WakeWordDetector:
    def __init__(self, config: dict):
        self.model_path = config.get("model_path", "")
        self.threshold = float(config.get("threshold", 0.5))
        self.sample_rate = int(config.get("sample_rate", 16000))
        self.window_seconds = 2
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._on_detected: Optional[Callable] = None
        self._error = False
        try:
            import onnxruntime  # noqa: F401
        except ImportError:
            self._error = True
            log.warning("onnxruntime missing: wake word disabled (mic button still works)")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def status(self) -> str:
        if self._error:
            return "error"
        if not self.is_running:
            return "stopped"
        return "paused" if self._paused.is_set() else "running"

    def start(self, on_detected: Callable) -> None:
        if self._error or self.is_running:
            return
        if not Path(self.model_path).is_file():
            log.warning("Wake word model file missing")
            self._error = True
            return
        self._on_detected = on_detected
        self._stop.clear()
        self._paused.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="WakeWord")
        self._thread.start()

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def _loop(self) -> None:
        try:
            import numpy as np
            from openwakeword.model import Model
            from .audio_utils import record_audio
            model = Model(wakeword_models=[self.model_path], inference_framework="onnx")
        except Exception as e:
            log.warning(f"Wake word init failed: {type(e).__name__}")
            self._error = True
            return
        while not self._stop.is_set():
            if self._paused.is_set():
                time.sleep(0.2)
                continue
            tmp = Path(tempfile.mkdtemp(prefix="raven_voice_")) / "w.wav"
            try:
                if not record_audio(self.window_seconds, self.sample_rate, tmp):
                    time.sleep(1.0)
                    continue
                if self._paused.is_set():  # paused during recording: discard
                    continue
                with wave.open(str(tmp), "rb") as w:
                    pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                hit = False
                for i in range(0, len(pcm) - _FRAME + 1, _FRAME):
                    scores = model.predict(pcm[i:i + _FRAME])
                    if scores and max(scores.values()) > self.threshold:
                        hit = True
                        break
                if hit and self._on_detected and not self._paused.is_set():
                    model.reset()
                    threading.Thread(target=self._on_detected, daemon=True).start()
                    time.sleep(1.0)
            except Exception as e:
                log.warning(f"Wake word loop error: {type(e).__name__}")
                time.sleep(1.0)
            finally:
                from .audio_utils import cleanup_temp_audio
                cleanup_temp_audio(tmp)