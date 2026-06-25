"""web-search · sidebar panel (DUI) — status + heavy-read policy switch.

Minimal left-slot panel so the extension registers a sidebar surface (platform deploy gate).
Shows that web research is active and lets the user flip the heavy-read policy in one tap.
"""
from __future__ import annotations

from app import ext
from imperal_sdk import ui

_POLICY_LABEL = {
    "ask": "Ask before heavy reads",
    "always": "Always read",
    "never_heavy": "Never heavy reads",
}
_POLICY_COLOR = {"ask": "gray", "always": "green", "never_heavy": "red"}


async def _policy(ctx) -> str:
    try:
        page = await ctx.store.query("ws_prefs", where={"owner_id": ctx.user.imperal_id}, limit=1)
        if page.data:
            return page.data[0].data.get("web_read_policy") or "ask"
    except Exception:
        pass
    return "ask"


@ext.panel("sidebar", slot="left", title="Web Search", icon="Search",
           refresh="on_event:web_read_policy.changed")
async def panel_sidebar(ctx, **kwargs) -> ui.UINode:
    """Left panel — web-research status + one-tap heavy-read policy switch."""
    policy = await _policy(ctx)

    def _btn(key: str, label: str) -> ui.UINode:
        return ui.Button(
            label,
            variant=("primary" if policy == key else "ghost"),
            size="sm",
            on_click=ui.Call("set_web_read_policy", policy=key),
        )

    return ui.Stack([
        ui.Markdown(
            "**Web research** is active across chat — search the web and read pages into "
            "clean Markdown. No setup needed: just ask Webbee to look something up."
        ),
        ui.Divider(label="Heavy-read policy"),
        ui.Badge(label=_POLICY_LABEL.get(policy, policy), color=_POLICY_COLOR.get(policy, "gray")),
        ui.Stack([
            _btn("ask", "Ask first"),
            _btn("always", "Always read"),
            _btn("never_heavy", "Never heavy"),
        ], gap=2),
    ], gap=3)
