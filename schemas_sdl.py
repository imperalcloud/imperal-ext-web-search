"""web-search — SDL entity classes (imperal-sdk 5.x).

Namespace: ws.* — custom roles, safe (not a reserved SDL namespace).
"""
from __future__ import annotations

from imperal_sdk import sdl
from imperal_sdk.sdl import field as sdl_field


class SearchResultItem(sdl.Entity):
    """One web-search candidate card (facts only — relevance is the LLM's job)."""

    kind: str = "search_result"
    url: str | None = sdl_field(role="ws.url")
    snippet: str | None = sdl_field(role="ws.snippet")
    published_date: str | None = sdl_field(role="ws.published_date")
    author: str | None = sdl_field(role="ws.author")
    score: float | None = sdl_field(role="ws.score")
    engine: str | None = sdl_field(role="ws.engine")


class SearchResultList(sdl.EntityList[SearchResultItem]):
    """web_search results — a real EntityList, never a dict wrapper."""

    pass


class PageContent(sdl.Entity):
    """A page read into clean Markdown + extraction metadata."""

    kind: str = "page_content"
    url: str | None = sdl_field(role="ws.url")
    final_url: str | None = sdl_field(role="ws.final_url")
    content: str | None = sdl_field(role="ws.content")
    source: str | None = sdl_field(role="ws.source")            # readable|pdf|jsonld|feed|links|rendered|office
    content_type: str | None = sdl_field(role="ws.content_type")
    lang: str | None = sdl_field(role="ws.lang")
    token_count: int | None = sdl_field(role="ws.token_count")
    word_count: int | None = sdl_field(role="ws.word_count")
    truncated: bool | None = sdl_field(role="ws.truncated")
    content_hash: str | None = sdl_field(role="ws.content_hash")   # sha256[:32] of content — dedup key
    outline: list | None = sdl_field(role="ws.outline")           # [{level, text}] full heading tree
    tables: list | None = sdl_field(role="ws.tables")             # [{headers, rows}] structured tables
    page_metadata: dict | None = sdl_field(role="ws.page_metadata")


class WsOpResult(sdl.Entity):
    """Generic confirmation — e.g. read-policy change."""

    kind: str = "ws_op"
    policy: str | None = sdl_field(role="ws.policy")
