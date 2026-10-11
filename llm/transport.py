"""LLM transport: Transport protocol, UrlLibTransport (real), FakeTransport (tests).

A transport sends ONE chat-completions request and returns the parsed JSON dict.
It raises TransportError (a CloudError) on any failure. Error messages are fixed
strings: they never contain the request body, the response text or the API key.
"""
from __future__ import annotations

import copy
import http.client
import json
import socket
import urllib.error
import urllib.request
from typing import Any, Optional, Protocol

from core.errors import CloudError

MAX_RESPONSE_BYTES = 2_000_000
MAX_ERROR_BYTES = 65_536


class TransportError(CloudError):
    """kind: 'http' | 'timeout' | 'connection' | 'bad_json' | 'other'.
    status: HTTP status or None. body: parsed JSON error body or None."""

    def __init__(self, message: str, status: Optional[int] = None,
                 kind: str = "http", body: Optional[dict] = None) -> None:
        super().__init__(message)
        self.status = status
        self.kind = kind
        self.body = body


class Transport(Protocol):
    def request(self, payload: dict) -> dict: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects: urllib would forward the Authorization header."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class UrlLibTransport:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._key = api_key
        self._timeout = float(timeout)
        self._opener = urllib.request.build_opener(_NoRedirect)

    def request(self, payload: dict) -> dict:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self._url, data=data, method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self._key}",
            },
        )
        try:
            with self._opener.open(req, timeout=self._timeout) as resp:
                raw = resp.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise TransportError(f"HTTP {exc.code}", status=exc.code, kind="http",
                                 body=self._error_body(exc)) from None
        except (socket.timeout, TimeoutError):
            raise TransportError("request timed out", kind="timeout") from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise TransportError("request timed out", kind="timeout") from None
            raise TransportError("connection failed", kind="connection") from None
        except (OSError, http.client.HTTPException):
            raise TransportError("connection failed", kind="connection") from None
        except Exception:
            raise TransportError("request failed", kind="other") from None

        if len(raw) > MAX_RESPONSE_BYTES:
            raise TransportError("response too large", kind="bad_json")
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise TransportError("malformed response", kind="bad_json") from None
        if not isinstance(body, dict):
            raise TransportError("malformed response", kind="bad_json")
        return body

    def _error_body(self, exc: urllib.error.HTTPError) -> Optional[dict]:
        """Parsed JSON error body, or None. Dropped if it echoes the key."""
        try:
            raw = exc.read(MAX_ERROR_BYTES)
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            return None
        if not isinstance(body, dict):
            return None
        if self._key and self._key in json.dumps(body, ensure_ascii=False):
            return None
        return body

    def __repr__(self) -> str:  # never shows the key
        return f"UrlLibTransport(url={self._url!r})"

    __str__ = __repr__


class FakeTransport:
    """Test double. Records every request; replays scripted items in order.

    Script item: a dict (returned) or an exception instance (raised).
    When the script is empty, `default` is used; if None, TransportError is raised.
    """

    def __init__(self, *script: Any, default: Optional[dict] = None) -> None:
        self._script: list = list(script)
        self.default = default
        self.requests: list[dict] = []

    def push(self, *items: Any) -> "FakeTransport":
        self._script.extend(items)
        return self

    @property
    def calls(self) -> int:
        return len(self.requests)

    def request(self, payload: dict) -> dict:
        self.requests.append(copy.deepcopy(payload))
        item = self._script.pop(0) if self._script else self.default
        if item is None:
            raise TransportError("no scripted response", kind="other")
        if isinstance(item, BaseException):
            raise item
        return copy.deepcopy(item)

    def dump_requests(self) -> str:
        """All recorded requests as one string (for leak scans)."""
        return json.dumps(self.requests, ensure_ascii=False)

    def __repr__(self) -> str:
        return f"FakeTransport(calls={self.calls})"

    __str__ = __repr__


# ---- helpers for tests -------------------------------------------------
def ok_response(content: Optional[str], model: str = "fake-model",
                prompt_tokens: int = 10, completion_tokens: int = 5,
                finish_reason: str = "stop") -> dict:
    return {
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": content},
                     "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


def http_error(status: int, message: str = "error") -> TransportError:
    return TransportError(f"HTTP {status}", status=status, kind="http",
                          body={"error": {"message": message, "code": status}})


def timeout_error() -> TransportError:
    return TransportError("request timed out", kind="timeout")


def connection_error() -> TransportError:
    return TransportError("connection failed", kind="connection")