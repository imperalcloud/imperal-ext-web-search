"""Web-search · bulk page reading.

Research is plural by nature: a search returns ten candidates and the next
honest step is "read the top three". Doing that one `read_url` call at a
time is not merely tedious — the reads run STRICTLY SEQUENTIALLY, so three
pages take three round trips of latency when they could have taken one.

`read_urls` reads several pages CONCURRENTLY and returns one combined
result.

Token economy is the hard constraint here, not an afterthought. A naive
bulk reader is the fastest way to blow a context window: five pages at the
8000-token default is 40k tokens in a single tool result. So:

  * `max_tokens` is the budget for the WHOLE batch, not per page. It is
    divided across the URLs, so reading more pages makes each page's slice
    smaller instead of multiplying the total;
  * `mode` defaults to 'main' (prose only) rather than 'full', because the
    batch case is nearly always "get the gist of these", not "give me every
    byte of five pages";
  * mode='outline' or 'metadata' stays available for cheap triage across
    many URLs before committing to a full read of one.

Failures are per URL. One dead link does not sink the batch: the pages that
read successfully come back, and the failures are listed with their reason.
That matters more here than elsewhere — a bulk read that returns an error
because the 4th of 5 links 404'd would waste the 3 pages already fetched.

Deliberately NOT bulk: the TOKEN-HEAVY readers (read_url_rendered,
read_document). Those exist behind an explicit per-page consent step
precisely because they are expensive; batching them would let one call
spend an unbounded amount of the user's tokens with a single approval.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Literal

from pydantic import BaseModel, Field

from imperal_sdk.chat import ActionResult

from app import chat
from handlers_search import _post_read

log = logging.getLogger("web_search.handlers_bulk")

_MAX_URLS = 10

# Floor for a per-page slice. Below roughly this, an extract is too
# truncated to answer anything and the read is wasted tokens.
_MIN_SLICE = 400


# ─── Models ───────────────────────────────────────────────────────────── #

class ReadUrlsParams(BaseModel):
    """Read SEVERAL pages in one call."""

    urls: list[str] = Field(
        ...,
        min_length=1,
        max_length=_MAX_URLS,
        description=(
            "The pages to read (http/https), up to 10. They are fetched "
            "CONCURRENTLY, so this is much faster than calling read_url "
            "once per page — always prefer it when you have several "
            "candidates from a search."
        ),
    )
    max_tokens: int = Field(
        default=12000, ge=1000, le=48000,
        description=(
            "Token budget for the WHOLE batch, split across the URLs — NOT "
            "per page. Reading more pages shrinks each page's slice rather "
            "than multiplying the total cost."
        ),
    )
    query: str | None = Field(
        default=None,
        description=(
            "Optional: the question you are trying to answer. Extraction is "
            "focused on it, which makes each page's smaller slice far more "
            "useful. Pass it whenever you have one."
        ),
    )
    mode: Literal["full", "main", "outline", "tables", "metadata"] = Field(
        default="main",
        description=(
            "TOKEN ECONOMY — what to return per page. Defaults to 'main' "
            "(prose only), which is the right choice for almost every batch. "
            "Use 'outline' or 'metadata' to triage many candidates cheaply "
            "before a full read of the one that matters; 'full' only for a "
            "small batch you genuinely need in full."
        ),
    )


class BulkPageResult(BaseModel):
    """One page's outcome inside a batch.

    `outline` and `tables` are carried alongside `content` because the cheap
    triage modes return their payload in those keys and leave `content`
    empty — dropping them would make mode='outline'/'tables' silently
    useless in a batch, which is exactly the mode a multi-URL read wants.
    """
    model_config = {"extra": "allow"}

    url: str = ""
    ok: bool = False
    title: str = ""
    content: str = ""
    token_count: int = 0
    content_hash: str = ""
    outline: list | None = None
    tables: list | None = None
    error: str = ""


class BulkReadResult(BaseModel):
    """Combined outcome of a bulk read."""
    model_config = {"extra": "allow"}

    pages: list[BulkPageResult] = Field(default_factory=list)
    succeeded: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    total: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_tokens: int = 0


# ─── Helpers ──────────────────────────────────────────────────────────── #

def _clean_urls(raw: list[str]) -> tuple[list[str], list[str]]:
    """Normalise, drop blanks, de-dupe, and reject non-http schemes.

    De-duplication matters: a search result list routinely contains the same
    page twice, and paying to read it twice is pure waste.
    """
    seen: set[str] = set()
    urls: list[str] = []
    bad: list[str] = []
    for item in raw:
        u = (item or "").strip()
        if not u:
            continue
        if not u.lower().startswith(("http://", "https://")):
            bad.append(f"{u} — not an http(s) URL")
            continue
        key = u.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        urls.append(u)
    return urls, bad


# ─── Handler ──────────────────────────────────────────────────────────── #

@chat.function(
    "read_urls",
    action_type="read",
    data_model=BulkReadResult,
    description=(
        "READ SEVERAL web pages in ONE call, concurrently — the bulk form of "
        "read_url. Use this whenever you want more than one page (e.g. the "
        "top 3 results of a search): it is much faster than calling read_url "
        "repeatedly. TOKEN ECONOMY: max_tokens is the budget for the WHOLE "
        "batch and is split across the pages, and mode defaults to 'main' "
        "(prose only) — use mode='outline' or 'metadata' to triage many "
        "candidates cheaply before a full read. Pass `query` to focus every "
        "extraction on your actual question. Dead or blocked links are "
        "reported per URL and never discard the pages that did read; if an "
        "important page comes back blocked, fall back to the single-page "
        "read_url for it, which can escalate to the heavy readers."
    ),
)
async def fn_read_urls(ctx, params: ReadUrlsParams) -> ActionResult:
    """Read many pages concurrently under ONE shared token budget."""
    urls, bad = _clean_urls(params.urls)
    if not urls:
        return ActionResult.error(
            "No readable URLs given. " + ("; ".join(bad) if bad else "")
        )

    # The budget is for the batch. Splitting it (rather than applying
    # max_tokens per page) is what keeps a 10-URL call from returning
    # 80k tokens.
    per_page = max(_MIN_SLICE, params.max_tokens // len(urls))

    async def _read_one(url: str) -> BulkPageResult:
        try:
            data, _code, err = await _post_read(
                ctx, "/v1/read", url, per_page, params.query, params.mode, 40,
            )
        except Exception as exc:                              # noqa: BLE001
            log.warning("bulk read %s: %s", url, exc)
            return BulkPageResult(url=url, ok=False, error=str(exc)[:160])
        if err:
            return BulkPageResult(url=url, ok=False, error=str(err)[:160])
        data = data or {}
        return BulkPageResult(
            url=url,
            ok=True,
            title=str(data.get("title") or url),
            content=str(data.get("content") or data.get("markdown") or ""),
            outline=(data.get("outline")
                     if isinstance(data.get("outline"), list) and data.get("outline")
                     else None),
            tables=(data.get("tables")
                    if isinstance(data.get("tables"), list) and data.get("tables")
                    else None),
            token_count=int(data.get("token_count") or 0),
            content_hash=str(data.get("content_hash") or ""),
        )

    # Concurrency is the entire point: sequential reads would make a 5-page
    # batch five round trips of latency. return_exceptions keeps one hard
    # failure from cancelling its siblings mid-flight.
    results = await asyncio.gather(
        *(_read_one(u) for u in urls), return_exceptions=True,
    )

    pages: list[BulkPageResult] = []
    for url, res in zip(urls, results):
        if isinstance(res, BaseException):
            log.warning("bulk read %s crashed: %s", url, res)
            pages.append(BulkPageResult(url=url, ok=False, error=str(res)[:160]))
        else:
            pages.append(res)

    ok = [p.url for p in pages if p.ok]
    failed = [f"{p.url} — {p.error}" for p in pages if not p.ok] + bad
    total_tokens = sum(p.token_count for p in pages if p.ok)

    data = BulkReadResult(
        pages=pages,
        succeeded=ok,
        failed=failed,
        total=len(pages) + len(bad),
        success_count=len(ok),
        failure_count=len(failed),
        total_tokens=total_tokens,
    )

    if not ok:
        return ActionResult.error(
            "None of those pages could be read. " + "; ".join(failed[:4]),
            retryable=True,
        )

    if failed:
        summary = (
            f"Read {len(ok)} of {len(pages) + len(bad)} pages "
            f"({total_tokens} tokens). Could not read: "
            + "; ".join(failed[:3])
        )
    else:
        summary = f"Read {len(ok)} pages ({total_tokens} tokens)."

    # Partial success stays a SUCCESS: the pages that were fetched are real
    # work and must not be thrown away because a sibling link was dead.
    return ActionResult.success(data=data, summary=summary)
