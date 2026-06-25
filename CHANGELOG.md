# Changelog

## [1.0.0] — 2026-06-25 — Initial: hidden system web-research extension

Extracted from `web-tools` into its own standalone **hidden system extension** (`system=True`,
no panels/skeleton/tray, no UI surface). Same `whm-web-tools-api` backend, same behaviour.

### Tools (5)
- `web_search` → `/v1/search` (Exa) — candidate cards as `EntityList[SearchResultItem]`; params:
  query, num_results, include_domains, recency_days, type, category.
- `read_url` → `/v1/read` — cheap reader; `mode` (full/main/outline/tables/metadata) token economy;
  surfaces content_hash/outline/tables/word_count; deterministic escalation on blocked/Office pages.
- `read_url_rendered` → `/v1/read_rendered` — ⚠️ TOKEN-HEAVY headless-Chromium reader.
- `read_document` → `/v1/read_document` — ⚠️ TOKEN-HEAVY Office-doc reader.
- `set_web_read_policy` — per-user heavy-read policy (ask/always/never_heavy) in `ws_prefs`.

### Notes
- `system=True` is gated by the Dev Portal first-party allowlist — to test-deploy before access is
  granted, set `system=False` in `app.py` (code otherwise identical).
- Error handling via `backend.py` `unwrap()`/`unwrap_full()` — never `raise_for_status()`; backend
  failures become retryable `ActionResult.error` facts (HTTP 200 + `{success:false}` contract).
- SDL namespace `ws.*`; store collection `ws_prefs` — disjoint from `web-tools`.
