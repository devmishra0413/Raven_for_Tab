"""Voice pipeline: wake word + STT + chat + TTS with one audio lock."""
import logging
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from .audio_utils import record_audio, cleanup_temp_audio, create_temp_wav_path, check_mic_permission
from .stt import WhisperSTT
from .tts import PiperTTS
from .wake_word import WakeWordDetector

log = logging.getLogger(__name__)
_JOB_TTL = 60


class VoicePipeline:
    def __init__(self, wake_word: WakeWordDetector, stt: WhisperSTT, tts: PiperTTS,
                 config: dict, on_text_ready: Callable[[str], str]):
        self.wake_word = wake_word
        self.stt = stt
        self.tts = tts
        self.config = config  # the "voice" sub-dict
        self.on_text_ready = on_text_ready
        self._audio_lock = threading.Lock()
        self._jobs: dict = {}
        self._jobs_lock = threading.Lock()
        a = config.get("audio", {})
        self.sample_rate = a.get("sample_rate", 16000)
        self.record_backend = a.get("record_backend", "termux-microphone-record")
        self.record_seconds = config.get("stt", {}).get("record_seconds", 8)

    # ---- lifecycle ----
    def start(self) -> None:
        if not self.config.get("wake_word", {}).get("enabled", True):
            return
        if self.wake_word and self.wake_word.status != "error":
            self.wake_word.start(self.handle_wake_word)
        else:
            log.warning("Wake word unavailable; mic button still works")

    def stop(self) -> None:
        if self.wake_word:
            self.wake_word.stop()
        with self._jobs_lock:
            self._jobs.clear()

    def _pause(self) -> None:
        if self.wake_word and self.wake_word.is_running:
            self.wake_word.pause()

    def _resume(self) -> None:
        if self.wake_word and self.wake_word.is_running:
            self.wake_word.resume()

    # ---- core: record + transcribe (caller holds the audio lock) ----
    def _listen(self):
        """Returns (text, error). text '' means nothing usable heard."""
        wav = create_temp_wav_path("voice_")
        try:
            if not record_audio(self.record_seconds, self.sample_rate, wav, self.record_backend):
                return "", "Recording failed"
            res = self.stt.transcribe(wav)
        finally:
            cleanup_temp_audio(wav)
        if not res.success:
            return "", res.error or "STT failed"
        text = (res.text or "").strip()
        return (text if len(text) >= 2 else ""), None  # transcript never logged

    # ---- wake word ----
    def handle_wake_word(self) -> None:
        if not self._audio_lock.acquire(blocking=False):
            return
        try:
            self._pause()
            text, err = self._listen()
        except Exception as e:
            log.warning(f"Voice error: {type(e).__name__}")
            text, err = "", "error"
        finally:
            self._resume()
            self._audio_lock.release()
        if err or not text:
            return
        try:
            reply = self.on_text_ready(text)  # sanitized inside chat pipeline
            if reply:
                self.speak_text(reply)
        except Exception as e:
            log.warning(f"Voice chat error: {type(e).__name__}")

    # ---- mic button ----
    def trigger_mic_button(self) -> str:
        job_id = uuid.uuid4().hex[:8]
        with self._jobs_lock:
            self._purge()
            self._jobs[job_id] = {"status": "pending", "text": None, "reply": None,
                                  "error": None, "ts": time.time()}
        threading.Thread(target=self._run_mic_job, args=(job_id,), daemon=True,
                         name=f"MicJob-{job_id}").start()
        return job_id

    def _run_mic_job(self, job_id: str) -> None:
        if not self._audio_lock.acquire(timeout=5.0):
            self._update(job_id, "error", error="Audio device busy")
            return
        try:
            self._pause()
            text, err = self._listen()
        except Exception as e:
            log.warning(f"Mic job error: {type(e).__name__}")
            text, err = "", "Voice processing failed"
        finally:
            self._resume()
            self._audio_lock.release()
        if err:
            self._update(job_id, "error", error=err)
            return
        if not text:
            self._update(job_id, "done", text="", reply="")
            return
        try:
            self._update(job_id, "pending", text=text)
            reply = self.on_text_ready(text)
            self._update(job_id, "done", text=text, reply=reply or "")
            if reply:
                self.speak_text(reply)
        except Exception as e:
            log.warning(f"Mic chat error: {type(e).__name__}")
            self._update(job_id, "error", error="Voice processing failed")

    def _update(self, job_id, status, text=None, reply=None, error=None) -> None:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["status"] = status
            if text is not None:
                job["text"] = text
            if reply is not None:
                job["reply"] = reply
            if error is not None:
                job["error"] = error

    def _purge(self) -> None:  # call with lock held
        cut = time.time() - _JOB_TTL
        for k in [k for k, j in self._jobs.items() if j["ts"] < cut]:
            del self._jobs[k]

    def get_mic_result(self, job_id: str):
        with self._jobs_lock:
            self._purge()
            job = self._jobs.get(job_id)
            return {k: v for k, v in job.items() if k != "ts"} if job else None

    # ---- TTS ----
    def speak_text(self, text: str) -> bool:
        if not self._audio_lock.acquire(timeout=10.0):
            return False
        try:
            self._pause()
            return self.tts.speak(text[:500]).success
        except Exception as e:
            log.warning(f"TTS error: {type(e).__name__}")
            return False
        finally:
            self._resume()
            self._audio_lock.release()


def run_voice_check(config) -> None:
    from .audio_utils import termux_microphone_record_available, termux_media_player_available
    v = config.get("voice", {})
    ok = lambda b: "PASS" if b else "FAIL"
    print("=== RAVEN Voice Check ===")
    print("termux-microphone-record:", ok(termux_microphone_record_available()))
    print("termux-media-player:", ok(termux_media_player_available()))
    print("ffmpeg (needed for WAV):", ok(bool(shutil.which("ffmpeg"))))
    print("mic permission:", ok(check_mic_permission()))
    try:
        import onnxruntime  # noqa: F401
        print("onnxruntime: PASS")
    except ImportError:
        print("onnxruntime: FAIL (pip install onnxruntime)")
    print("wake word model:", ok(Path(v.get("wake_word", {}).get("model_path", "")).is_file()))
    s, t = v.get("stt", {}), v.get("tts", {})
    print("whisper binary:", ok(bool(shutil.which(s.get("binary", "whisper-cli")))))
    print("whisper model:", ok(Path(s.get("model_path", "")).is_file()))
    print("piper binary:", ok(bool(shutil.which(t.get("binary", "piper")))))
    print("piper model:", ok(Path(t.get("model_path", "")).is_file()))
    print("piper config:", ok(Path(t.get("model_config", "")).is_file()))