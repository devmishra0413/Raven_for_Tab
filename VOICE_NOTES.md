# RAVEN Voice Notes (Phase 8)

Status: repair in progress. Wake word streaming is untested on a real device. The mic button is the reliable path.

## 1. Pipeline and RAM flow
Order: wake word -> record -> Whisper (exits) -> sanitize -> chat -> Piper (exits) -> play.

- The wake word model (onnx, ~1 MB) stays loaded.
- `whisper-cli` and `piper` run as separate subprocesses, started on demand and exited after use, so they are never in RAM together (4 GB limit).

## 2. Audio lock
A single `threading.Lock` guards the mic and speaker. The wake loop, mic button and TTS all use the same device. Without the lock, recording during playback (or two recordings at once) fails or captures RAVEN's own voice. The wake word is paused while the lock is held.

## 3. Wake word streaming on Termux
- `termux-microphone-record` cannot stream. It records asynchronously to a file (AAC/m4a). Sub-second chunks (80 ms) do not work because process spawn and mic open dominate.
- Current approach: record 2 s windows, convert with ffmpeg to 16 kHz WAV, feed 1280-sample frames to openWakeWord.
- Known gap: about 1 s between windows, so a wake word spoken in a gap is missed. Confidence: LOW-MEDIUM.
- `/dev/snd` is not accessible without root on Android. PyAudio needs a custom build.
- Requires: `pkg install ffmpeg`.
- Alternatives: mic button (works now), a small Android app or Termux:Widget shortcut, or Porcupine with a native bridge.

## 4. Whisper (Hindi/Hinglish)
- `base`: fast, but weak on Hindi and code-mixed speech. Hinglish often comes out in Devanagari or with spelling errors.
- `small`: better accuracy, about 2-3x slower on Helio G99.
- Use language `hi` for Hindi-only speech. `auto` can misdetect.

## 5. Piper (Hindi TTS)
Robotic but intelligible. English words inside Hindi text may be mispronounced. Replies are capped at 500 characters.

## 6. Degraded modes
If `onnxruntime` is missing, wake word status becomes `error` and one warning is logged. Mic button, STT and TTS keep working.

## 7. Custom "Hey Raven" wake word
Train with the openWakeWord automatic training Colab (https://github.com/dscripka/openWakeWord, section "Training New Models"). Place the `.onnx` in `models/` and set `voice.wake_word.model_path`.

## 8. Security
- Audio never leaves the device.
- Recordings go to private temp dirs (`raven_voice_*`) and are deleted right after STT. TTS WAVs are deleted right after playback.
- Transcripts, audio paths and reply text are never logged.
- Transcribed text goes through the same `sanitize()` path as typed text before any cloud call.
- Voice mode auto-sends masked text (no preview) and declines sensitive-topic messages.

## 9. Tests
- Planned in `tests/voice/`, fully mocked (no mic, Whisper, Piper or onnxruntime needed).
- To cover: audio lock, `raven_voice_*` cleanup, onnxruntime-missing status, 500-char TTS cap, sensitive-topic decline, `sanitize()` before cloud.
- Current state: no voice tests are collected yet.
- Run: `python -m pytest tests/voice -v -rs`

## 10. Known limitations
- Wake word accuracy on Indian accents is unknown until tested on device.
- Whisper Hindi accuracy is about 85% and varies with accent.
- Android may kill RAVEN under very low RAM.