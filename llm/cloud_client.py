"""OpenRouter chat client: retries, model fallback, response validation.

- chat(payload) never mutates `payload`; it adds "model" per attempt on a copy.
- Messages are FIXED strings: no request body, response text or API key.
- 4xx policy: 401/403 stop at once (CloudAuthError). 408/429/5xx/timeout/
  connection/bad JSON/empty reply are retried (max_attempts_per_model) and then
  the next model is tried. Other 4xx (400/402/404/413/422...) are treated as
  "this model can't serve it": skip to the next model, no retries.
- Optional `cloud.provider` config (verified in OpenRouter docs, see notes):
  {"data_collection": "allow"|"deny", "zdr": true|false}
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

from core.errors import CloudError, ConfigError
from llm.transport import Transport, TransportError

_PROVIDER_KEYS = ("data_collection", "zdr")


class CloudAuthError(CloudError):
    """401/403: do not retry; the user must check the key."""


@dataclass(frozen=True)
class ChatResult:
    content: str = field(repr=False)
    model: str = ""
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    truncated: bool = False


class _Fail(Exception):
    def __init__(self, action: str, desc: str) -> None:
        super().__init__(desc)
        self.action, self.desc = action, desc


def _int(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def _classify(status: Optional[int], kind: str = "http") -> str:
    """-> 'auth' | 'retry' | 'next'."""
    if status in (401, 403):
        return "auth"
    if status is None or status in (408, 429) or status >= 500:
        return "retry"
    if kind in ("timeout", "connection", "bad_json"):
        return "retry"
    return "next"


class OpenRouterClient:
    def __init__(
        self,
        transport: Transport,
        config: Any,
        sleep: Callable[[float], None] = time.sleep,
        secrets: Iterable[str] = (),
        backoff_base: float = 0.5,
    ) -> None:
        cloud = config["cloud"]
        self.transport = transport
        self.models: list[str] = list(cloud.get("models", []))
        self.attempts = max(1, int(cloud.get("max_attempts_per_model", 2)))
        self._sleep = sleep
        self._backoff_base = backoff_base
        self._secrets = [s for s in secrets if isinstance(s, str) and len(s) >= 4]
        self.provider = self._check_provider(cloud.get("provider"))

    @staticmethod
    def _check_provider(p: Any) -> Optional[dict]:
        if p in (None, {}):
            return None
        if not isinstance(p, dict) or any(k not in _PROVIDER_KEYS for k in p):
            raise ConfigError("'cloud.provider' may only contain: " + ", ".join(_PROVIDER_KEYS))
        if "data_collection" in p and p["data_collection"] not in ("allow", "deny"):
            raise ConfigError("'cloud.provider.data_collection' must be 'allow' or 'deny'")
        if "zdr" in p and not isinstance(p["zdr"], bool):
            raise ConfigError("'cloud.provider.zdr' must be true or false")
        return dict(p)

    # ---- public -------------------------------------------------------
    def chat(self, payload: dict) -> ChatResult:
        if not self.models:
            raise CloudError("No models configured.")
        last = "no attempt made"
        for model in self.models:
            for attempt in range(1, self.attempts + 1):
                body = {**payload, "model": model}  # shallow copy: payload untouched
                if self.provider:
                    body["provider"] = dict(self.provider)
                t0 = time.monotonic()
                try:
                    return self._parse(self.transport.request(body), model, t0)
                except _Fail as f:
                    action, last = f.action, f"{model}: {f.desc}"
                except TransportError as e:
                    action = _classify(e.status, e.kind)
                    last = f"{model}: " + (f"HTTP {e.status}" if e.status else e.kind)
                except Exception:
                    action, last = "retry", f"{model}: request failed"
                if action == "auth":
                    raise CloudAuthError(self._scrub(
                        "Authentication failed. Check your API key (env var)."))
                if action == "next":
                    break
                if attempt < self.attempts:
                    self._sleep(min(self._backoff_base * 2 ** (attempt - 1), 4.0))
        raise CloudError(self._scrub(f"All models failed. Last error: {last}"))

    # ---- response validation --------------------------------------------
    def _parse(self, resp: Any, model: str, t0: float) -> ChatResult:
        if not isinstance(resp, dict):
            raise _Fail("retry", "malformed response")
        err = resp.get("error")
        if err:  # error object inside an HTTP 200 body
            code = _int(err.get("code")) if isinstance(err, dict) else None
            raise _Fail(_classify(code, "other") if code else "retry",
                        f"error in response" + (f" (code {code})" if code else ""))
        choices = resp.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise _Fail("retry", "empty choices")
        choice = choices[0]
        if choice.get("error"):
            raise _Fail("retry", "error in choice")
        msg = choice.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, list):  # content parts
            content = "".join(p.get("text", "") for p in content
                              if isinstance(p, dict) and isinstance(p.get("text"), str))
        if not isinstance(content, str) or not content.strip():
            raise _Fail("retry", "empty content")
        usage = resp.get("usage") if isinstance(resp.get("usage"), dict) else {}
        return ChatResult(
            content=content,
            model=model,
            prompt_tokens=_int(usage.get("prompt_tokens")),
            completion_tokens=_int(usage.get("completion_tokens")),
            latency_ms=int((time.monotonic() - t0) * 1000),
            truncated=choice.get("finish_reason") == "length",
        )

    def _scrub(self, text: str) -> str:
        for s in self._secrets:
            text = text.replace(s, "[REDACTED]")
        return text

    def __repr__(self) -> str:
        return f"OpenRouterClient(models={len(self.models)})"

    __str__ = __repr__