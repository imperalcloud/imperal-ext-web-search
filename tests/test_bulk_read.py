"""Functional tests for bulk page reading (`read_urls`).

The batch reader has one failure mode that matters far more than the
others: blowing the context window. Five pages at the single-page default
would be 40k tokens in one tool result. So the budget behaviour is pinned
first and hardest.

Also pinned:

  * every URL is actually read — not just the first;
  * the reads run CONCURRENTLY (the whole point of the tool);
  * one dead link does not sink the batch — pages that read successfully
    still come back, which is the difference between wasting 3 good fetches
    and keeping them;
  * duplicate URLs collapse, so the same page is not fetched twice.
"""
import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers_bulk as hb  # noqa: E402


# ─── harness ──────────────────────────────────────────────────────────── #

class _Reader:
    """Stands in for the reader service.

    Records the max_tokens each URL was read with (so budget behaviour is
    observable) and tracks concurrency by watching how many reads are in
    flight at once.
    """

    def __init__(self, failing=None, delay=0.01):
        self.failing = set(failing or ())
        self.delay = delay
        self.reads: list[tuple[str, int, str]] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def __call__(self, ctx, path, url, max_tokens, query, mode, timeout):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delay)
            self.reads.append((url, max_tokens, mode))
            if url in self.failing:
                return {}, "404", "not found"
            return (
                {
                    "title": f"Title of {url}",
                    "content": f"content of {url}",
                    "token_count": 100,
                    "content_hash": f"h-{url}",
                },
                None,
                None,
            )
        finally:
            self.in_flight -= 1

    @property
    def urls(self) -> list[str]:
        return [u for u, _, _ in self.reads]


class _Ctx:
    class user:
        imperal_id = "imp_u_TESTUSER"


@pytest.fixture
def ctx():
    return _Ctx()


def _patch(monkeypatch, reader):
    monkeypatch.setattr(hb, "_post_read", reader)


# ─── the basic promise ────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_reads_every_url_in_one_call(ctx, monkeypatch):
    reader = _Reader()
    _patch(monkeypatch, reader)

    res = await hb.fn_read_urls(
        ctx,
        hb.ReadUrlsParams(urls=[
            "https://a.example/1",
            "https://b.example/2",
            "https://c.example/3",
        ]),
    )

    assert res.status == "success"
    assert sorted(reader.urls) == [
        "https://a.example/1", "https://b.example/2", "https://c.example/3",
    ]
    assert res.data.success_count == 3


@pytest.mark.asyncio
async def test_the_reads_actually_run_concurrently(ctx, monkeypatch):
    """Sequential reads are what this tool exists to replace."""
    reader = _Reader(delay=0.05)
    _patch(monkeypatch, reader)

    await hb.fn_read_urls(
        ctx,
        hb.ReadUrlsParams(urls=[
            "https://a.example/1",
            "https://b.example/2",
            "https://c.example/3",
        ]),
    )

    assert reader.max_in_flight > 1, (
        "reads ran one after another — the batch reader gains nothing "
        f"over looping read_url (max in flight: {reader.max_in_flight})"
    )


# ─── token economy (the expensive failure mode) ───────────────────────── #

@pytest.mark.asyncio
async def test_the_token_budget_is_for_the_whole_batch_not_per_page(ctx, monkeypatch):
    """5 pages x the single-page default would be 40k tokens in one result."""
    reader = _Reader()
    _patch(monkeypatch, reader)

    await hb.fn_read_urls(
        ctx,
        hb.ReadUrlsParams(
            urls=[f"https://e.example/{i}" for i in range(5)],
            max_tokens=10000,
        ),
    )

    total = sum(tok for _, tok, _ in reader.reads)
    assert total <= 10000, (
        f"the batch asked for {total} tokens against a 10000 budget — "
        "the budget is being applied per page instead of per batch"
    )


@pytest.mark.asyncio
async def test_more_pages_means_a_smaller_slice_each(ctx, monkeypatch):
    reader = _Reader()
    _patch(monkeypatch, reader)

    await hb.fn_read_urls(
        ctx, hb.ReadUrlsParams(urls=["https://a.example/1"], max_tokens=8000),
    )
    one_page = reader.reads[0][1]

    reader2 = _Reader()
    _patch(monkeypatch, reader2)
    await hb.fn_read_urls(
        ctx,
        hb.ReadUrlsParams(
            urls=[f"https://f.example/{i}" for i in range(4)], max_tokens=8000,
        ),
    )
    four_pages = reader2.reads[0][1]

    assert four_pages < one_page, (
        "reading four pages must give each a smaller slice, not the same "
        f"budget four times ({one_page} vs {four_pages})"
    )


@pytest.mark.asyncio
async def test_batch_reading_defaults_to_prose_not_the_whole_page(ctx, monkeypatch):
    """'Read these three' means the gist, not every byte of three pages."""
    reader = _Reader()
    _patch(monkeypatch, reader)

    await hb.fn_read_urls(
        ctx, hb.ReadUrlsParams(urls=["https://a.example/1", "https://b.example/2"]),
    )

    assert {mode for _, _, mode in reader.reads} == {"main"}


@pytest.mark.asyncio
async def test_cheap_triage_mode_is_still_available(ctx, monkeypatch):
    reader = _Reader()
    _patch(monkeypatch, reader)

    await hb.fn_read_urls(
        ctx,
        hb.ReadUrlsParams(
            urls=["https://a.example/1", "https://b.example/2"], mode="outline",
        ),
    )

    assert {mode for _, _, mode in reader.reads} == {"outline"}


# ─── partial success ──────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_one_dead_link_does_not_waste_the_good_fetches(ctx, monkeypatch):
    reader = _Reader(failing={"https://dead.example/x"})
    _patch(monkeypatch, reader)

    res = await hb.fn_read_urls(
        ctx,
        hb.ReadUrlsParams(urls=[
            "https://a.example/1",
            "https://dead.example/x",
            "https://c.example/3",
        ]),
    )

    assert res.status == "success", (
        "two pages read fine — returning an error would throw them away"
    )
    assert res.data.success_count == 2
    assert res.data.failure_count == 1
    assert any("dead.example" in f for f in res.data.failed), res.data.failed


@pytest.mark.asyncio
async def test_every_url_failing_is_an_error(ctx, monkeypatch):
    reader = _Reader(failing={"https://a.example/1", "https://b.example/2"})
    _patch(monkeypatch, reader)

    res = await hb.fn_read_urls(
        ctx,
        hb.ReadUrlsParams(urls=["https://a.example/1", "https://b.example/2"]),
    )

    assert res.status == "error"


# ─── de-duplication ───────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_the_same_url_is_not_fetched_twice(ctx, monkeypatch):
    reader = _Reader()
    _patch(monkeypatch, reader)

    res = await hb.fn_read_urls(
        ctx,
        hb.ReadUrlsParams(urls=[
            "https://a.example/1",
            "https://a.example/1",
            "https://b.example/2",
        ]),
    )

    assert reader.urls.count("https://a.example/1") == 1, reader.urls
    assert res.data.success_count == 2


# ─── content comes back ───────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_the_pages_content_is_actually_returned(ctx, monkeypatch):
    """A reader that reports success but returns no text is useless."""
    reader = _Reader()
    _patch(monkeypatch, reader)

    res = await hb.fn_read_urls(
        ctx, hb.ReadUrlsParams(urls=["https://a.example/1"]),
    )

    pages = res.data.pages
    assert len(pages) == 1
    assert "content of https://a.example/1" in str(pages[0])


@pytest.mark.asyncio
async def test_outline_mode_payload_survives_the_batch(ctx, monkeypatch):
    """The cheap triage modes return their payload in `outline`/`tables`
    and leave `content` empty. Dropping those keys would make the very
    mode a multi-URL read wants silently useless."""

    class _OutlineReader(_Reader):
        async def __call__(self, ctx, path, url, max_tokens, query, mode, timeout):
            self.reads.append((url, max_tokens, mode))
            return (
                {
                    "title": f"Title of {url}",
                    "content": "",
                    "outline": [{"level": 2, "text": "Pricing"}],
                    "token_count": 12,
                },
                None,
                None,
            )

    reader = _OutlineReader()
    _patch(monkeypatch, reader)

    res = await hb.fn_read_urls(
        ctx,
        hb.ReadUrlsParams(urls=["https://a.example/1"], mode="outline"),
    )

    page = res.data.pages[0]
    assert page.outline, "the outline was dropped — mode='outline' returns nothing"
    assert page.outline[0]["text"] == "Pricing"
