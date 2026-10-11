"""Phase 3 config: load, validate, safe defaults.

Error messages name the offending KEY only, never its value (a value could be
a pasted secret). The API key is read from an environment variable only.
"""
from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any, Dict

from core.errors import ConfigError

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULTS: Dict[str, Dict[str, Any]] = {
    "cloud": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "models": [],
        "timeout_seconds": 30,
        "max_attempts_per_model": 2,
        "max_tokens": 800,
    },
    "privacy": {"preview": "always"},
    "session": {"history_messages": 6, "context_k": 5, "context_max_chars": 1200},
    "paths": {"db": "data/raven.db"},
        "scheduler": {"enabled": False, "check_interval_seconds": 30,
                  "briefing_time": "08:00", "briefing_enabled": True,
                  "briefing_include_facts": True, "briefing_include_reminders": True,
                  "briefing_max_facts": 5, "timezone_offset_hours": 5.5},
    "voice": {"enabled": False,
              "wake_word": {"enabled": True, "model_path": "models/hey_jarvis.onnx",
                            "threshold": 0.5, "chunk_ms": 80},
              "stt": {"binary": "whisper-cli", "model_path": "models/ggml-base.bin",
                      "language": "auto", "timeout_seconds": 30, "record_seconds": 8},
              "tts": {"binary": "piper", "model_path": "models/hi_IN-female.onnx",
                      "model_config": "models/hi_IN-female.onnx.json",
                      "speed": 1.0, "timeout_seconds": 15},
              "audio": {"sample_rate": 16000, "channels": 1,
                        "record_backend": "termux-microphone-record"}},
}


ALLOWED_PREVIEWS = ("always", "when_masked", "never")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_FORBIDDEN_CLOUD_KEYS = ("api_key", "apikey", "key", "token", "secret", "authorization")   



def _num(sec: dict, name: str, key: str, lo: float, hi: float, integer: bool = True) -> None:
    v = sec[key]
    ok = isinstance(v, int) if integer else isinstance(v, (int, float))
    if isinstance(v, bool) or not ok or not (lo <= v <= hi):
        kind = "an integer" if integer else "a number"
        raise ConfigError(f"'{name}.{key}' must be {kind} between {lo:g} and {hi:g}")


class Config:
    """Dict-like: config["cloud"] -> section dict."""

    def __init__(self, cfg: Dict[str, Any]) -> None:
        if not isinstance(cfg, dict):
            raise ConfigError("config must be a JSON object")
        merged = copy.deepcopy(DEFAULTS)
        for name, default in DEFAULTS.items():
            given = cfg.get(name)
            if given is None:
                continue
            if not isinstance(given, dict):
                raise ConfigError(f"'{name}' must be an object")
            merged[name].update(copy.deepcopy(given))
        self.cfg = merged
        self._validate()

    # ---- loading ------------------------------------------------------
    @classmethod
    def load(cls, path: str = "config.json") -> "Config":
        p = Path(path)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        if not p.is_file():
            raise ConfigError(
                f"Config file not found: {p.name}. Copy config.example.json to "
                f"config.json and fill in your models.")
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{p.name} is not valid JSON (line {exc.lineno}).") from None
        except (OSError, UnicodeDecodeError):
            raise ConfigError(f"Could not read {p.name}.") from None
        return cls(raw)

    # ---- validation ---------------------------------------------------
    def _validate(self) -> None:
        c, p, s, paths = (self.cfg[k] for k in ("cloud", "privacy", "session", "paths"))

        for bad in c:
            if str(bad).lower() in _FORBIDDEN_CLOUD_KEYS:
                raise ConfigError(
                    "Do not store an API key in config. Set it as an environment variable.")

        if not isinstance(c["base_url"], str) or not re.match(r"^https?://\S+$", c["base_url"]):
            raise ConfigError("'cloud.base_url' must be an http(s) URL")

        env = c["api_key_env"]
        if (not isinstance(env, str) or not _ENV_NAME.match(env)
                or env.lower().startswith("sk")):
            raise ConfigError(
                "'cloud.api_key_env' must be the NAME of an environment variable "
                "(e.g. OPENROUTER_API_KEY), not the key itself")

        models = c["models"]
        if not isinstance(models, list) or not models:
            raise ConfigError("'cloud.models' must be a non-empty list of model names")
        for m in models:
            if not isinstance(m, str) or not m.strip():
                raise ConfigError("'cloud.models' entries must be non-empty strings")
            if re.match(r"^<.*>$", m.strip()):
                raise ConfigError(
                    "'cloud.models' still has placeholder names. Fill in real model names.")
    def _deep(base: dict, over: dict) -> None:
        for k, v in over.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                _deep(base[k], v)
            else:
                base[k] = copy.deepcopy(v)    
    
        _num(c, "cloud", "timeout_seconds", 1, 300, integer=False)
        _num(c, "cloud", "max_attempts_per_model", 1, 5)
        _num(c, "cloud", "max_tokens", 1, 8000)

        if p["preview"] not in ALLOWED_PREVIEWS:
            raise ConfigError(
                "'privacy.preview' must be one of: " + ", ".join(ALLOWED_PREVIEWS))

        _num(s, "session", "history_messages", 0, 50)
        _num(s, "session", "context_k", 0, 20)
        _num(s, "session", "context_max_chars", 0, 10000)

        if not isinstance(paths["db"], str) or not paths["db"].strip():
            raise ConfigError("'paths.db' must be a non-empty path")

    # ---- access -------------------------------------------------------
    @property
    def db_path(self) -> str:
        """DB path; relative paths resolve against the project root."""
        p = Path(self.cfg["paths"]["db"])
        return str(p if p.is_absolute() else PROJECT_ROOT / p)

    def __getitem__(self, key: str) -> Any:
        return self.cfg[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.cfg.get(key, default)

    def __repr__(self) -> str:
        return f"Config(sections={sorted(self.cfg)})"

    __str__ = __repr__


def get_api_key(cfg: Config) -> str:
    """API key from the environment ONLY. Never logged, never in messages."""
    env = cfg["cloud"]["api_key_env"]
    key = (os.environ.get(env) or "").strip()
    if not key:
        raise ConfigError(
            f"Environment variable {env} is not set. Export it before starting RAVEN.")
    return key