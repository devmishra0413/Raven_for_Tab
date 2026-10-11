"""
Whisper STT for RAVEN - Speech-to-Text using whisper.cpp.

Offline transcription using whisper.cpp binary.
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class STTResult:
    """Result from speech-to-text transcription."""
    text: str
    language: str | None
    success: bool
    error: str | None


class WhisperSTT:
    """
    Whisper speech-to-text using whisper.cpp subprocess.
    
    Runs whisper-cli binary with model from config.
    """
    
    def __init__(self, config: dict):
        self.binary = config.get("binary", "whisper-cli")
        self.model_path = config.get("model_path", "")
        self.language = config.get("language", "auto")
        self.timeout_seconds = config.get("timeout_seconds", 30)
        
        # Verify binary exists
        if not shutil.which(self.binary):
            log.warning(f"Whisper binary not found: {self.binary}")
    
    def transcribe(self, audio_path: Path) -> STTResult:
        """
        Transcribe audio file to text.
        
        Args:
            audio_path: Path to WAV audio file
        
        Returns:
            STTResult with transcription text
        """
        if not audio_path.exists():
            return STTResult(
                text="",
                language=None,
                success=False,
                error="Audio file not found"
            )
        
        if not Path(self.model_path).exists():
            return STTResult(
                text="",
                language=None,
                success=False,
                error="Model file not found"
            )
        
        try:
            # Build whisper-cli command
            # -m: model, -f: input file, -l: language, 
            # --output-txt: output text file, --no-prints: suppress logs
            cmd = [self.binary, "-m", str(self.model_path), "-f", str(audio_path),
                   "-l", self.language, "-nt", "-np"]            
            # Run whisper with timeout
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds
            )
            
            if result.returncode != 0:
                log.warning(f"Whisper STT failed with return code {result.returncode}")
                return STTResult(
                    text="",
                    language=None,
                    success=False,
                    error="Transcription failed"
                )
            
            # Parse stdout for transcribed text
            # whisper-cli outputs transcription to stdout
            text = result.stdout.strip()
            
            # Try to extract language if detected
            # whisper-cli may output language info in stderr or stdout
            language = self.language
            
            return STTResult(
                text=text,
                language=language,
                success=True,
                error=None
            )
            
        except subprocess.TimeoutExpired:
            log.warning("Whisper STT timed out")
            return STTResult(
                text="",
                language=None,
                success=False,
                error="Transcription timed out"
            )
        except Exception as e:
            log.warning(f"Whisper STT error: {type(e).__name__}")
            return STTResult(
                text="",
                language=None,
                success=False,
                error="Transcription error"
            )
