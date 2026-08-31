"""web-search · capture_page — server-side visual capture (webbee-eyes cloud tier).

Separate module (no god-files): the cloud sibling of the terminal's
webbee-eyes organ. POSTs /v1/capture on the web-tools api-server, ships the
PNG into the system File Reader through ctx.files (ai_vision can then READ
the screenshot back), and returns facts-only JSON (console errors, failed
requests, a11y role tree, meta). The brain judges; this organ only senses.
"""
from __future__ import annotations

import base64
import hashlib
from typing import Literal

from pydantic import BaseModel, Field

from imperal_sdk import ActionResult

from app import chat, WEB_SEARCH_API_URL
from backend import unwrap
from schemas_sdl import PageContent


class CapturePageParams(BaseModel):
    """Capture-page parameters."""
    url: str = Field(..., min_length=1, description="URL to capture (http/https, public target).")
    viewport: Literal["desktop", "laptop", "tablet", "mobile"] = Field(
        default="desktop", description="Screen shape: desktop 1920x1080, laptop 1366x768, "
                                       "tablet 768x1024, mobile 390x844.")
    full_page: bool = Field(default=False,
                            description="True = full scroll-height capture (bigger PNG, slower).")
    wait_ms: int = Field(default=0, ge=0, le=10000,
                         description="Extra settle delay before the screenshot (max 10s).")
    actions: list[dict] | None = Field(
        default=None,
        description="Optional pre-screenshot actions on the SAME page, in order — "
                    "[{type:click|type|press|scroll|wait|waitfor|goto|eval, ...}] — e.g. "
                    "[{\"type\":\"type\",\"selector\":\"#email\",\"text\":\"a@b.c\"},"
                    "{\"type\":\"click\",\"selector\":\"button\"}]. Stops at the first "
                    "failing action; the log lands in the result.")
    with_screenshot: bool = Field(
        default=True,
        description="True: upload the PNG into File Reader (returns file_id; ai_vision reads it "
                    "back via read_files). False: facts-only (console/network/a11y/meta).")


@chat.function("capture_page", action_type="read",
               data_model=PageContent,
               description="SEE a web page — real screenshot + machine FACTS from a headless Chromium "
                           "on the api-server (webbee-eyes cloud tier, for panel/Telegram — the terminal "
                           "uses its local webbee-eyes organ instead). Returns console errors, failed "
                           "requests, an accessibility role tree (also your click/type targeting map), "
                           "page meta and, unless with_screenshot=false, a file_id whose screenshot you "
                           "can READ with file-reader read_files (ai_vision). Optional pre-capture "
                           "actions (click/type/press/scroll/wait/waitfor/goto/eval) run on the SAME "
                           "page, so you can log into a form or open a tab before the shot. Use to "
                           "VERIFY what you built, to check how a page really looks, or to debug layout "
                           "— never as a text reader (read_url is for content).")
async def fn_capture_page(ctx, params: CapturePageParams) -> ActionResult:
    """Headless-Chromium visual capture → File Reader (ai_vision) + facts JSON."""
    body: dict = {"url": params.url, "viewport": params.viewport,
                  "full_page": params.full_page, "wait_ms": params.wait_ms}
    if params.actions:
        body["actions"] = params.actions[:20]
    try:
        resp = await ctx.http.post(f"{WEB_SEARCH_API_URL}/v1/capture", json=body, timeout=60)
    except Exception as exc:
        return ActionResult.error(
            f"Could not reach the capture service for {params.url} ({exc}).", retryable=True)
    data, err = unwrap(resp, "Page capture failed")
    if err:
        return ActionResult.error(err, retryable=True)

    facts = {
        "url": data.get("url"), "final_url": data.get("final_url"),
        "status": data.get("status"), "viewport": data.get("viewport"),
        "console_errors": (data.get("console") or {}).get("errors", []),
        "console_warnings": (data.get("console") or {}).get("warnings", []),
        "failed_requests": data.get("failed_requests", []),
        "a11y": data.get("a11y", []),
        "actions": data.get("actions", []),
        "meta": data.get("meta", {}),
    }

    file_id = None
    png_note = ""
    if params.with_screenshot and data.get("png_base64"):
        try:
            png = base64.b64decode(data["png_base64"])
            digest = hashlib.sha256(png).hexdigest()[:10]
            host = (data.get("final_url") or params.url).split("/")[2][:60]
            fname = f"capture-{host}-{data.get('viewport', 'desktop')}-{digest}.png"
            files = getattr(ctx, "files", None)
            if files is not None:
                out = await files.ingest(png, fname, mime_type="image/png")
                file_id = out.get("document_id") or out.get("id") or out.get("file_id")
                facts["screenshot_file_id"] = file_id
                facts["screenshot_png_bytes"] = len(png)
                png_note = f"; screenshot ingested to File Reader (document_id={file_id}) — read it back with file-reader read_files"
            else:
                png_note = "; ctx.files unavailable — screenshot dropped (facts still returned)"
        except Exception as exc:
            png_note = f"; screenshot ingest failed ({exc}) — facts still returned"

    import json
    facts_json = json.dumps(facts, ensure_ascii=False)
    page = PageContent(
        id=facts["final_url"] or params.url,
        title=f"capture: {(facts['meta'] or {}).get('title') or facts['final_url'] or params.url}"[:300],
        kind="page_content",
        url=params.url,
        final_url=facts["final_url"],
        content=facts_json,
        source="capture",
        content_type="application/json",
    )
    errs = len(facts["console_errors"])
    failed = len(facts["failed_requests"])
    summary = (f"Captured {facts['final_url']} [{data.get('status')}] at {params.viewport}"
               f"{': ' + str(errs) + ' console error(s), ' + str(failed) + ' failed request(s)' if (errs or failed) else ', clean'}"
               f"{png_note}")
    return ActionResult.success(data=page, summary=summary)
