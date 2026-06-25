"""web-search · Skeleton — per-user web-research status (SDK 5.x).

Cache-warmup read by the LLM each turn. Every Imperal extension declares a @ext.skeleton
(its `skeleton_refresh_*` tool is the platform's per-extension registration/status anchor) —
this one just surfaces the user's heavy-read policy. Scalars only; degrades to defaults.
"""
from __future__ import annotations

from app import ext
from imperal_sdk import ActionResult


@ext.skeleton(
    "web_search",
    ttl=300,
    description="Web Search status — the user's heavy-read policy (ask/always/never_heavy). "
                "Web research works with no setup: web_search to find pages, read_url to read them.",
)
async def on_refresh(ctx) -> ActionResult:
    """Per-user web-research status — read policy only (scalars, degrade to defaults)."""
    policy = "ask"
    try:
        page = await ctx.store.query("ws_prefs", where={"owner_id": ctx.user.imperal_id}, limit=1)
        if page.data:
            policy = page.data[0].data.get("web_read_policy") or "ask"
    except Exception:
        policy = "ask"
    return ActionResult.success(
        data={"read_policy": policy, "ready": True},
        summary=f"Web Search ready — heavy-read policy: {policy}.",
    )
