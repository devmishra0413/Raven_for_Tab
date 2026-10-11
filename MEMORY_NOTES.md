# RAVEN Memory Notes (Phase 2)

Design decisions, schema, search approach and limitations.

## 1. Schema
- **Facts:** normalized content plus a sha256 hash for deduplication.
- **Entities:** name, type and JSON aliases.
- **Episodes:** summaries for recall (used from Phase 4).

## 2. Search
- FTS5 with the `unicode61` tokenizer. It handles Devanagari combining marks (matras) correctly on SQLite 3.53.1, so custom `tokenchars` were not needed.
- Falls back to `LIKE` if FTS5 is unavailable.
- All user input goes through `text_utils.sanitize_fts_query()`, which strips quotes, operators, colons and parentheses to prevent FTS5 syntax errors and injection.

## 3. Sensitivity rules
- On `add()`, Phase 1 `topic_guard` and `regex_filter` auto-mark `sensitivity=1`. An explicit value overrides the auto value.
- `sensitivity=1` facts are never returned by `build_cloud_context()`.
- Deduplication never lowers an existing `sensitivity=1`, but can raise it.
- `repr()` and `str()` of a fact hide its content.

## 4. Phase 4 requirements (auto-extraction)
- `MemoryManager.add()` accepts `status='pending'` (implemented).
- `MemoryManager.confirm()` commits suggested facts (implemented).
- `update()` handles fact refinement (implemented).

## 5. Tests
- Location: `tests/memory_tests/`
- Result at last run: 136 passed (manager, db, entities, search, context, export/import).
- Gap: the fallback when the `privacy` package is missing is untested.
- Run: `python -m pytest tests/memory_tests -v`

## 6. Known limitations
- The DB is not encrypted.
- If the `privacy` package is missing, `build_cloud_context()` only truncates, with no sanitization.
- `sanitize_fts_query` forces OR between tokens, so complex boolean queries are not supported.
- FTS5 indexing time on very large datasets should be watched.