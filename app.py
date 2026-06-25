"""web-search · System web-research capability for Webbee (SDK 5.x / SDL).

HIDDEN SYSTEM EXTENSION — no panels, no skeleton, no tray, no UI surface. Just @chat.function
tools that call the web-tools-api backend. `system=True` marks it platform-managed (auto-installed,
hidden from marketplace, not uninstallable). NOTE: the Dev Portal gates `system=True` behind a
first-party author allowlist — until SeeU is allowlisted, flip to `system=False` to test-deploy as
a normal (iconless) extension; the code is otherwise identical.
"""
from __future__ import annotations

import os

from imperal_sdk import Extension
from imperal_sdk.chat import ChatExtension

# ─── Extension Setup ──────────────────────────────────────────────────────── #

ext = Extension(
    "web-search",
    version="1.0.1",
    display_name="Web Search",
    description=(
        "Live web research for Webbee — search the web and read pages into clean Markdown. "
        "System capability: available to every chat, no setup."
    ),
    icon="icon.svg",                 # V21 requires an icon asset; not shown for a system app
    actions_explicit=True,
    system=True,                     # platform-managed, hidden; Dev Portal gates publish by allowlist
    capabilities=["store:read", "store:write"],
)

# Same backend as web-tools (shared whm-web-tools-api). Override via env for self-hosted deployments.
WEB_SEARCH_API_URL = os.getenv("WEB_SEARCH_API_URL", "https://api.webhostmost.com/web-tools")

# SDK 5.x: ChatExtension is a @chat.function bundle. LLM guidance lives in the per-function
# descriptions + this bundle description.
chat = ChatExtension(
    ext=ext,
    tool_name="tool_web_search_chat",
    description=(
        "WEB RESEARCH — read the live web. "
        "web_search=find pages for a query (candidate cards url+title+snippet; does NOT read them); "
        "read_url=cheap reader, ONE page → clean Markdown (always try first; supports mode for token economy: "
        "metadata/outline to triage, full/tables on winners); "
        "read_url_rendered=⚠️TOKEN-HEAVY headless-Chromium reader for JS/bot-protected pages; "
        "read_document=⚠️TOKEN-HEAVY reader for Office docs (.docx/.xlsx/.pptx); "
        "set_web_read_policy=remember the user's heavy-read preference (ask/always/never_heavy). "
        "Loop: web_search → pick the 2–3 best url(s) → read_url each; if read_url errors, read the NEXT "
        "candidate; for 'today/latest' pass recency_days. If read_url says a page is blocked or is an Office "
        "doc, surface what you already found and ASK before using the heavy readers — unless policy is 'always'. "
        "Each read returns content_hash — don't re-ingest identical content you already read this conversation."
    ),
)


# ─── Lifecycle ────────────────────────────────────────────────────────────── #

@ext.health_check
async def health(ctx) -> dict:
    try:
        resp = await ctx.http.get(f"{WEB_SEARCH_API_URL}/v1/health")
        return {"status": "ok" if resp.status_code == 200 else "degraded", "version": ext.version}
    except Exception:
        return {"status": "degraded", "version": ext.version}
