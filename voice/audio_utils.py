"""Audio helpers: record (termux), play, cleanup. Never logs paths."""
import logging
import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path

log = logging.getLogger(__name__)
_TMP_PREFIX = "raven_voice_"
_mic_cache = {"t": 0.0, "ok": False}


def termux_microphone_record_available() -> bool:
    return shutil.which("termux-microphone-record") is not None


def termux_media_player_available() -> bool:
    return shutil.which("termux-media-player") is not None


def record_audio(duration_seconds: int, sample_rate: int, output_path: Path,
                 backend: str = "termux-microphone-record") -> bool:
    if backend != "termux-microphone-record" or not termux_microphone_record_available():
        log.warning("Recording backend unavailable")
        return False
    if not shutil.which("ffmpeg"):
        log.warning("ffmpeg missing (pkg install ffmpeg): cannot make WAV")
        return False
    tmp = Path(tempfile.mkdtemp(prefix="raven_rec_"))
    raw = tmp / "rec.m4a"
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["termux-microphone-record", "-f", str(raw), "-l", str(duration_seconds),
                        "-e", "aac", "-r", str(sample_rate), "-c", "1"],
                       capture_output=True, timeout=10)
        time.sleep(duration_seconds + 1)  # command returns immediately; recording is async
        subprocess.run(["termux-microphone-record", "-q"], capture_output=True, timeout=10)
        if not raw.exists() or raw.stat().st_size == 0:
            return False
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                            "-ar", str(sample_rate), "-ac", "1", str(output_path)],
                           capture_output=True, timeout=30)
        return r.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0
    except Exception as e:
        log.warning(f"Recording error: {type(e).__name__}")
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _wav_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 3.0


def play_audio(path: Path, wait: bool = True) -> bool:
    if not termux_media_player_available() or not path.exists():
        return False
    try:
        r = subprocess.run(["termux-media-player", "play", str(path)],
                           capture_output=True, timeout=10)
        if r.returncode != 0:
            return False
        if wait:  # play is async: wait so the caller doesn't delete the file mid-play
            time.sleep(_wav_seconds(path) + 0.5)
        return True
    except Exception as e:
        log.warning(f"Playback error: {type(e).__name__}")
        return False


def check_mic_permission() -> bool:
    """1s test recording; cached 60s so status polling doesn't keep recording."""
    if time.time() - _mic_cache["t"] < 60:
        return _mic_cache["ok"]
    tmp = Path(tempfile.mkdtemp(prefix="raven_mic_"))
    ok = False
    try:
        ok = record_audio(1, 16000, tmp / "t.wav")
    except Exception:
        ok = False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    _mic_cache.update(t=time.time(), ok=ok)
    return ok


def cleanup_temp_audio(path: Path) -> None:
    """Delete temp audio and its private temp dir."""
    try:
        if path is None:
            return
        if path.exists():
            path.unlink()
        if path.parent.name.startswith(_TMP_PREFIX):
            shutil.rmtree(path.parent, ignore_errors=True)
    except Exception as e:
        log.warning(f"Temp cleanup failed: {type(e).__name__}")


def create_temp_wav_path(prefix: str = "raven_") -> Path:
    d = Path(tempfile.mkdtemp(prefix=_TMP_PREFIX))
    return d / f"{prefix}{int(time.time() * 1000)}.wav"