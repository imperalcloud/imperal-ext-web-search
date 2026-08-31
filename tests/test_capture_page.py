"""Functional tests for the `capture_page` tool (webbee-eyes cloud tier).

Pinned behaviour:

  * params map onto the /v1/capture body (viewport/full_page/wait/actions,
    timeout 60s — the browser tier is heavier than read but bounded);
  * the returned data_model carries FACTS as JSON (console, failed reqs,
    a11y, meta) — facts-only, the brain judges;
  * a screenshot is ingested into File Reader via ctx.files and its
    document_id is surfaced, so ai_vision can read it back;
  * with_screenshot=false ingests nothing (facts-only mode);
  * a ctx without ctx.files degrades gracefully: facts still returned;
  * backend failure (HTTP error / success:false / transport raise)
    → retryable ActionResult.error, never a crash.
"""
import asyncio
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers_capture as hc  # noqa: E402

_PNG_RAW = b"\x89PNG\r\n\x1a\n" + b"0" * 128
_PNG = base64.b64encode(_PNG_RAW).decode()

_GOOD_BODY = {
    "success": True,
    "data": {
        "url": "https://example.com",
        "final_url": "https://example.com/",
        "status": 200, "viewport": "desktop", "full_page": False,
        "png_base64": _PNG, "png_bytes": len(_PNG_RAW),
        "console": {"errors": ["boom"], "warnings": []},
        "failed_requests": [{"url": "https://x/y.js", "status": 404}],
        "a11y": ["h1: Example Domain"],
        "actions": [], "meta": {"title": "Example Domain"},
        "query_time_ms": 500,
    },
}


class _Resp:
    """Minimal httpx.Response stand-in (unwrap only calls .json())."""

    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


class _Http:
    """Records the /v1/capture call and serves a canned response."""

    def __init__(self, body=_GOOD_BODY, status_code=200, raise_exc=None):
        self.body = body
        self.status_code = status_code
        self.raise_exc = raise_exc
        self.calls = []

    async def post(self, url, json=None, timeout=None):
        self.calls.append((url, json, timeout))
        if self.raise_exc is not None:
            raise self.raise_exc
        return _Resp(self.body, self.status_code)


class _Files:
    def __init__(self):
        self.ingested = []

    async def ingest(self, content, filename, mime_type=None):
        self.ingested.append((filename, len(content), mime_type))
        return {"document_id": 4242}


class _Ctx:
    def __init__(self, http=None, with_files=True):
        self.http = http or _Http()
        self.files = _Files() if with_files else None


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_params_map_to_capture_body():
    ctx = _Ctx()
    params = hc.CapturePageParams(
        url="https://example.com", viewport="mobile", full_page=True,
        wait_ms=300, actions=[{"type": "click", "selector": "#go"}])
    res = _run(hc.fn_capture_page(ctx, params))
    url, body, timeout = ctx.http.calls[0]
    assert url.endswith("/v1/capture")
    assert body["url"] == "https://example.com"
    assert body["viewport"] == "mobile"
    assert body["full_page"] is True
    assert body["wait_ms"] == 300
    assert body["actions"] == [{"type": "click", "selector": "#go"}]
    assert timeout == 60
    assert res.summary.startswith("Captured https://example.com/")


def test_no_actions_key_when_omitted():
    ctx = _Ctx()
    _run(hc.fn_capture_page(ctx, hc.CapturePageParams(url="https://example.com")))
    _url, body, _t = ctx.http.calls[0]
    assert "actions" not in body


def test_facts_are_returned_as_json_in_entity():
    ctx = _Ctx()
    res = _run(hc.fn_capture_page(ctx, hc.CapturePageParams(url="https://example.com")))
    facts = json.loads(res.data.content)
    assert facts["status"] == 200
    assert facts["console_errors"] == ["boom"]
    assert facts["failed_requests"] == [{"url": "https://x/y.js", "status": 404}]
    assert facts["a11y"] == ["h1: Example Domain"]
    assert facts["meta"]["title"] == "Example Domain"
    assert res.data.source == "capture"


def test_screenshot_ingested_to_file_reader_and_id_surfaced():
    ctx = _Ctx()
    res = _run(hc.fn_capture_page(ctx, hc.CapturePageParams(url="https://example.com")))
    (fname, size, mime), = ctx.files.ingested
    assert mime == "image/png"
    assert fname.startswith("capture-example.com-desktop-") and fname.endswith(".png")
    assert size == len(_PNG_RAW)
    facts = json.loads(res.data.content)
    assert facts["screenshot_file_id"] == 4242
    assert facts["screenshot_png_bytes"] == len(_PNG_RAW)
    assert "document_id=4242" in res.summary


def test_no_screenshot_mode_ingests_nothing():
    ctx = _Ctx()
    _run(hc.fn_capture_page(
        ctx, hc.CapturePageParams(url="https://example.com", with_screenshot=False)))
    assert ctx.files.ingested == []


def test_missing_files_ctx_degrades_gracefully():
    ctx = _Ctx(with_files=False)
    res = _run(hc.fn_capture_page(ctx, hc.CapturePageParams(url="https://example.com")))
    facts = json.loads(res.data.content)
    assert "screenshot_file_id" not in facts          # no crash, facts still there
    assert facts["status"] == 200
    assert "screenshot dropped" in res.summary


def test_backend_success_false_is_retryable_error():
    body = {"success": False, "error": {"code": "UPSTREAM_HTTP_ERROR", "message": "upstream returned HTTP 502"}}
    ctx = _Ctx(http=_Http(body=body))
    res = _run(hc.fn_capture_page(ctx, hc.CapturePageParams(url="https://example.com")))
    assert res.status == "error" and res.retryable is True
    assert "502" in res.error
    assert res.error_code == "CAPTURE_BACKEND_ERROR"
    assert ctx.files.ingested == []


def test_transport_raise_is_retryable_error():
    ctx = _Ctx(http=_Http(raise_exc=RuntimeError("conn refused")))
    res = _run(hc.fn_capture_page(ctx, hc.CapturePageParams(url="https://example.com")))
    assert res.status == "error" and res.retryable is True
    assert "Could not reach the capture service" in res.error
    assert "conn refused" in res.error
    assert res.error_code == "CAPTURE_SERVICE_UNREACHABLE"
