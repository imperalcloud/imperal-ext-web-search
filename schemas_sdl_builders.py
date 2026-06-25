"""web-search — SDL builder helpers (imperal-sdk 5.x).

Each function converts raw web-tools-api data into the corresponding SDL entity for
ActionResult.data. Handlers import ONLY from this module — it re-exports the entity classes too.
"""
from __future__ import annotations

from schemas_sdl import (
    SearchResultItem, SearchResultList, PageContent, WsOpResult,
)

__all__ = [
    "SearchResultItem", "SearchResultList", "PageContent", "WsOpResult",
    "build_search_result", "build_search_result_list", "build_page_content", "build_ws_op",
]


def build_search_result(r: dict) -> SearchResultItem:
    url = r.get("url") or ""
    return SearchResultItem(
        id=url,
        title=(r.get("title") or url or "result")[:300],
        kind="search_result",
        url=url or None,
        snippet=r.get("snippet"),
        published_date=r.get("published_date"),
        author=r.get("author"),
        score=r.get("score"),
        engine=r.get("engine") or "exa",
    )


def build_search_result_list(data: dict) -> SearchResultList:
    """Wrap backend SearchData into a SearchResultList EntityList."""
    raw = data.get("results") or []
    items = [build_search_result(r) for r in raw if isinstance(r, dict) and r.get("url")]
    return SearchResultList(items=items, total=data.get("count", len(items)))


def build_page_content(d: dict) -> PageContent:
    """Wrap backend ReadData into a PageContent entity."""
    url = d.get("url") or ""
    final_url = d.get("final_url") or url
    meta = d.get("metadata")
    outline = d.get("outline")
    tables = d.get("tables")
    return PageContent(
        id=final_url or url or "page",
        title=(d.get("title") or final_url or url or "page")[:300],
        kind="page_content",
        url=url or None,
        final_url=final_url or None,
        content=d.get("content") or "",
        source=d.get("source"),
        content_type=d.get("content_type"),
        lang=d.get("lang"),
        token_count=d.get("token_count") or 0,
        word_count=d.get("word_count"),
        truncated=bool(d.get("truncated", False)),
        content_hash=d.get("content_hash"),
        outline=outline if isinstance(outline, list) and outline else None,
        tables=tables if isinstance(tables, list) and tables else None,
        page_metadata=meta if isinstance(meta, dict) and meta else None,
    )


def build_ws_op(op_id: str, title: str, policy: str | None = None) -> WsOpResult:
    return WsOpResult(id=op_id, title=title, kind="ws_op", policy=policy)
