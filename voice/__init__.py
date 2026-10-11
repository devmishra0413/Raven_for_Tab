"""
Voice module for RAVEN.

Provides speech recognition, text-to-speech, and wake word detection
for offline voice interaction.
"""

from .audio_utils import (
    record_audio,
    play_audio,
    check_mic_permission,
    cleanup_temp_audio,
    create_temp_wav_path,
)
from .stt import WhisperSTT
from .tts import PiperTTS
from .wake_word import WakeWordDetector
from .pipeline import VoicePipeline

__all__ = [
    "record_audio",
    "play_audio",
    "check_mic_permission",
    "cleanup_temp_audio",
    "create_temp_wav_path",
    "WhisperSTT",
    "PiperTTS",
    "WakeWordDetector",
    "VoicePipeline",
]
