# web-search — Imperal system extension

**Hidden system web-research capability for Webbee.** No UI (no panels, no icon shown) — pure
`@chat.function` tools that call the shared `whm-web-tools-api` backend.

- **app_id:** `web-search` · **SDK:** imperal-sdk 5.x · **`system=True`** (platform-managed, hidden)
- **Backend:** `https://api.webhostmost.com/web-tools` (env `WEB_SEARCH_API_URL`) — endpoints
  `/v1/search`, `/v1/read`, `/v1/read_rendered`, `/v1/read_document` (already live)

## Tools
| Function | Backend | Notes |
|---|---|---|
| `web_search` | `POST /v1/search` | candidate cards; recency_days/type/category |
| `read_url` | `POST /v1/read` | cheap reader; `mode` token economy; content_hash dedup; auto-escalation |
| `read_url_rendered` | `POST /v1/read_rendered` | ⚠️ TOKEN-HEAVY (Chromium) |
| `read_document` | `POST /v1/read_document` | ⚠️ TOKEN-HEAVY (Office docs) |
| `set_web_read_policy` | store `ws_prefs` | ask / always / never_heavy |

## Files
```
app.py                  Extension(system=True) + ChatExtension (no panels/skeleton)
main.py                 entry point — import order + sys.modules purge
backend.py              unwrap()/unwrap_full()/error_message() — envelope normalizer
schemas_sdl.py          SearchResultItem / SearchResultList / PageContent / WsOpResult
schemas_sdl_builders.py builders
handlers_search.py      the 5 @chat.function tools
icon.svg                required asset (V21); not shown for a system app
imperal.json            generated manifest (`imperal build .`)
```

## Build / deploy
```bash
python3 -m py_compile *.py
imperal build .        # regenerate imperal.json
imperal validate .     # must be green
git add -A && git commit -m "..." && git push origin main
# Dev Portal → Deploy. NOTE: publishing system=True needs the first-party allowlist;
# until then set system=False in app.py to test-deploy.
```
