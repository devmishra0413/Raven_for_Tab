# RAVEN Brain Notes (Phase 3)

Orchestrator, cloud client, session, CLI, preview and audit.

## 1. Design
- The session vault is shared across all messages. `sanitize()` from Phase 1 accepts an optional vault and reuses it. This was the only change made to Phase 1, and all Phase 1 tests still passed.
- The orchestrator calls `privacy.sanitize()` directly, so it must supply the vault.
- `preview_payload()` shows exactly what will go to the cloud and asks the user to Send or Cancel.
- `AuditLogger` writes to the Phase 2 `audit_log` table. No schema change.
- `llm/transport.py` defines the Transport protocol. Tests use `FakeTransport`.
- `OpenRouterClient` is a thin wrapper with retries and model switching. HTTP 401/403 is treated as an auth failure.
- The system prompt is hard-coded (can move to config later).
- Requests send only `model`, `messages` and `max_tokens`. No `data_policy` or provider options, because they could not be confirmed.
- User-visible errors are cleaned and never leak secrets.

## 2. Auth
PIN/token auth was removed from the project. The API is open and relies on binding to `127.0.0.1` only.

## 3. Tests
- Currently `tests/core/` has one test (config file exists).
- Pending: orchestrator flow (sanitize -> preview -> cloud -> restore), session, audit, cloud client with `FakeTransport` (retry, model switching, 401/403, no secret in error text).
- API chat routes are tested in `tests/api_tests/` (6 passing).
- Run: `python -m pytest tests/core tests/api_tests -v`

## 4. Known limitations
- The DB is not encrypted.
- No stream handling.
- The system prompt is static.
- Retry/back-off timing has no direct test. It is only covered indirectly by error-injection tests.
- URL query secrets (e.g. `?token=abc123`) are not masked yet. A `SECRET` pattern is pending in `privacy/regex_filter.py`. The matching test is currently failing.