"""
Piper TTS for RAVEN - Text-to-Speech using offline piper.

Generates speech audio from text using piper binary.
"""

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class TTSResult:
    """Result from text-to-speech generation."""
    success: bool
    audio_path: Path | None
    error: str | None


class PiperTTS:
    """
    Piper text-to-speech for offline voice synthesis.
    
    Generates WAV audio from text using piper binary.
    """
    
    def __init__(self, config: dict):
        self.binary = config.get("binary", "piper")
        self.model_path = config.get("model_path", "")
        self.model_config = config.get("model_config", "")
        self.speed = config.get("speed", 1.0)
        self.timeout_seconds = config.get("timeout_seconds", 15)
        
        # Verify binary exists
        if not shutil.which(self.binary):
            log.warning(f"Piper binary not found: {self.binary}")
    
    def speak(self, text: str) -> TTSResult:
        import shutil
        from .audio_utils import play_audio, cleanup_temp_audio, create_temp_wav_path
        if not text.strip():
            return TTSResult(success=True, audio_path=None, error=None)
        if len(text) > 500:
            text = text[:497] + "..."
        temp_wav = create_temp_wav_path("tts_")
        try:
            cmd = [self.binary, "--model", self.model_path, "--config", self.model_config,
                   "--output_file", str(temp_wav),
                   "--length_scale", str(1.0 / self.speed) if self.speed > 0 else "1.0"]
            result = subprocess.run(cmd, input=text, capture_output=True, text=True,
                                    timeout=self.timeout_seconds)
            if result.returncode != 0 or not temp_wav.exists():
                return TTSResult(success=False, audio_path=None, error="TTS generation failed")
            if play_audio(temp_wav, wait=True):
                return TTSResult(success=True, audio_path=None, error=None)
            return TTSResult(success=False, audio_path=None, error="Audio playback failed")
        except subprocess.TimeoutExpired:
            return TTSResult(success=False, audio_path=None, error="TTS timed out")
        except Exception as e:
            log.warning(f"Piper TTS error: {type(e).__name__}")
            return TTSResult(success=False, audio_path=None, error="TTS error")
        finally:
            cleanup_temp_audio(temp_wav)
    
    def generate_audio(self, text: str) -> TTSResult:
        """
        Generate audio file from text without playing.
        
        Args:
            text: Text to convert (max 500 chars)
        
        Returns:
            TTSResult with audio path if successful
        """
        if not text.strip():
            return TTSResult(success=True, audio_path=None, error=None)
        
        # Truncate to 500 chars
        if len(text) > 500:
            text = text[:497] + "..."
        
        # Create temp WAV file
        temp_wav = Path(tempfile.mkdtemp()) / "piper_output.wav"
        
        try:
            cmd = [
                self.binary,
                "--model", self.model_path,
                "--config", self.model_config,
                "--output_file", str(temp_wav),
                "--length_scale", str(1.0 / self.speed) if self.speed > 0 else "1.0"
            ]
            
            result = subprocess.run(
                cmd,
                input=text,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds
            )
            
            if result.returncode != 0 or not temp_wav.exists():
                return TTSResult(
                    success=False,
                    audio_path=None,
                    error="TTS generation failed"
                )
            
            return TTSResult(
                success=True,
                audio_path=temp_wav,
                error=None
            )
            
        except Exception as e:
            log.warning(f"Piper TTS error: {type(e).__name__}")
            return TTSResult(
                success=False,
                audio_path=None,
                error="TTS error"
            )