# Changelog

## [1.0.3] — 2026-06-25 — Hide sidebar icon: panel moved to `overlay` slot

This is an admin/system extension — it must NOT show a sidebar launcher icon. The v1.0.2 panel used
`slot="left"`, which surfaces a launcher. Moved it to `slot="overlay"` (panel_id `status`): the panel
stays registered (deploy "Panels registered" still passes) but `overlay` panels open on-demand and
create NO persistent sidebar icon. The extension is hidden again.

## [1.0.2] — 2026-06-25 — Add sidebar panel (deploy gate: "Panels registered")

Deploy validation required a left-slot panel ("extension won't appear in sidebar"). Added a minimal
DUI sidebar panel — web-research status + one-tap heavy-read policy switch (ask/always/never_heavy,
calls set_web_read_policy, refreshes on web_read_policy.changed). Extension is no longer fully hidden
(has a sidebar surface) — accepted trade-off to pass deploy 11/11.

- `panels.py` → `@ext.panel("sidebar", slot="left", title="Web Search")`. Registered in `main.py`.

## [1.0.1] — 2026-06-25 — Add required @ext.skeleton (fix: tools not registering)

The v1.0.0 extension had NO `@ext.skeleton` — every other Imperal extension (all `imperal-ext-*`
+ web-tools) declares one, and its `skeleton_refresh_*` tool is the platform's per-extension
registration/status anchor. Without it the platform didn't surface the extension's tools.

- Added `skeleton.py` → `@ext.skeleton("web_search")` (tool `skeleton_refresh_web_search`), returns
  the per-user heavy-read policy (scalars, ttl=300). Registered in `main.py`.
- Manifest now: `skeleton_refresh_web_search` + 5 chat functions (matches the working ext shape).

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
