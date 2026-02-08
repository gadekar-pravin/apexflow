"""News router -- v2 with ALLOW_LOCAL_WRITES gate.

Changes from v1:
- POST/DELETE that modify settings gated by ALLOW_LOCAL_WRITES env var
- Replaced print() with logger
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import socket
from datetime import UTC, datetime
from html import escape as html_escape
from typing import Any
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config.settings_loader import load_settings, save_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/news", tags=["news"])

ALLOW_LOCAL_WRITES = os.environ.get("ALLOW_LOCAL_WRITES", "").lower() in ("1", "true", "yes")

# Default News Sources
DEFAULT_SOURCES: list[dict[str, Any]] = [
    {"id": "hn", "name": "Hacker News", "url": "https://news.ycombinator.com", "type": "api", "enabled": True},
    {
        "id": "arxiv",
        "name": "arXiv CS.AI",
        "url": "https://arxiv.org/list/cs.AI/recent",
        "type": "rss",
        "feed_url": "http://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=30",
        "enabled": True,
    },
    {
        "id": "karpathy",
        "name": "Andrej Karpathy",
        "url": "https://twitter.com/karpathy",
        "type": "rss",
        "feed_url": "https://nitter.net/karpathy/rss",
        "enabled": True,
    },
    {
        "id": "willison",
        "name": "Simon Willison",
        "url": "https://simonwillison.net/",
        "type": "rss",
        "feed_url": "https://simonwillison.net/atom/entries/",
        "enabled": True,
    },
]


def _require_writes() -> None:
    if not ALLOW_LOCAL_WRITES:
        raise HTTPException(status_code=403, detail="Local writes disabled. Set ALLOW_LOCAL_WRITES=1.")


def _validate_url(url: str) -> None:
    """Validate that a URL is safe to fetch (prevents SSRF)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Only http/https URLs are allowed")
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL: no hostname")
    try:
        for _family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise HTTPException(
                    status_code=400, detail="URLs pointing to internal/private networks are not allowed"
                )
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="Could not resolve hostname") from None


def _safe_request(method: str, url: str, *, max_redirects: int = 10, **kwargs: Any) -> requests.Response:
    """SSRF-safe request that validates every redirect target."""
    kwargs["allow_redirects"] = False
    for _ in range(max_redirects):
        resp = requests.request(method, url, **kwargs)
        if resp.is_redirect or resp.is_permanent_redirect:
            location = resp.headers.get("Location", "")
            if not location:
                break
            url = urljoin(resp.url, location)
            _validate_url(url)
            method = "GET"  # redirects switch to GET
        else:
            return resp
    raise HTTPException(status_code=400, detail="Too many redirects")


def get_news_settings() -> dict[str, Any]:
    settings = load_settings()
    if "news" not in settings:
        settings["news"] = {"sources": DEFAULT_SOURCES}
        if ALLOW_LOCAL_WRITES:
            save_settings()

    # Migration: Fix broken Arxiv URL
    sources: list[dict[str, Any]] = settings["news"]["sources"]
    dirty = False
    for s in sources:
        if s["id"] == "arxiv" and (
            s.get("feed_url", "") == "https://rss.arxiv.org/rss/cs.AI"
            or s.get("feed_url", "") == "http://export.arxiv.org/rss/cs.AI"
            or "rss.arxiv.org" in s.get("feed_url", "")
        ):
            s["feed_url"] = (
                "http://export.arxiv.org/api/query?search_query=cat:cs.AI"
                "&sortBy=submittedDate&sortOrder=descending&max_results=30"
            )
            dirty = True

    if dirty and ALLOW_LOCAL_WRITES:
        logger.info("Automatically fixed broken Arxiv URL")
        save_settings()

    result: dict[str, Any] = settings["news"]
    return result


class NewsSource(BaseModel):
    id: str
    name: str
    url: str
    type: str
    feed_url: str | None = None
    enabled: bool = True


class NewsItem(BaseModel):
    id: str
    title: str
    url: str
    source_name: str
    timestamp: str
    points: int | None = None
    comments: int | None = None
    summary: str | None = None


class AddSourceTabsRequest(BaseModel):
    name: str
    url: str


@router.get("/sources")
async def get_sources() -> dict[str, Any]:
    news_settings = get_news_settings()
    return {"status": "success", "sources": news_settings["sources"]}


@router.post("/sources")
async def add_source(request: AddSourceTabsRequest) -> dict[str, Any]:
    _require_writes()
    _validate_url(request.url)
    news_settings = get_news_settings()

    if any(s["url"] == request.url for s in news_settings["sources"]):
        raise HTTPException(status_code=400, detail="Source already exists")

    feed_url: str | None = None
    try:
        response = _safe_request("GET", request.url, timeout=5)
        soup = BeautifulSoup(response.text, "html.parser")

        rss_link = soup.find("link", type="application/rss+xml") or soup.find("link", type="application/atom+xml")

        if rss_link:
            feed_url = rss_link.get("href")
            if feed_url and not feed_url.startswith("http"):
                feed_url = urljoin(request.url, feed_url)
    except Exception as e:
        logger.warning("Feed discovery failed for %s: %s", request.url, e)

    source_id = request.name.lower().replace(" ", "_")
    if any(s["id"] == source_id for s in news_settings["sources"]):
        raise HTTPException(status_code=400, detail="A source with this name already exists")

    new_source: dict[str, Any] = {
        "id": source_id,
        "name": request.name,
        "url": request.url,
        "type": "rss" if feed_url else "scrape",
        "feed_url": feed_url,
        "enabled": True,
    }

    news_settings["sources"].append(new_source)
    save_settings()
    return {"status": "success", "source": new_source}


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str) -> dict[str, str]:
    _require_writes()
    news_settings = get_news_settings()
    news_settings["sources"] = [s for s in news_settings["sources"] if s["id"] != source_id]
    save_settings()
    return {"status": "success"}


# Simple in-memory cache for HN stories
_hn_cache: dict[str, Any] = {"items": [], "timestamp": 0}
HN_CACHE_TTL = 300


async def fetch_hn() -> list[NewsItem]:
    """Fetch Hacker News top stories with caching and parallel requests."""
    import time

    global _hn_cache

    if time.time() - _hn_cache["timestamp"] < HN_CACHE_TTL and _hn_cache["items"]:
        return _hn_cache["items"]  # type: ignore[no-any-return]

    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://hacker-news.firebaseio.com/v0/topstories.json",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                story_ids = (await resp.json())[:20]

            async def fetch_story(sid: int) -> NewsItem | None:
                try:
                    async with session.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as sresp:
                        story = await sresp.json()
                        if story:
                            return NewsItem(
                                id=f"hn_{sid}",
                                title=story.get("title", ""),
                                url=story.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                                source_name="Hacker News",
                                timestamp=datetime.fromtimestamp(story.get("time", 0), tz=UTC).isoformat(),
                                points=story.get("score"),
                                comments=len(story.get("kids", [])) if "kids" in story else 0,
                            )
                except Exception as e:
                    logger.warning("Error fetching story %s: %s", sid, e)
                return None

            items = await asyncio.gather(*[fetch_story(sid) for sid in story_ids])
            filtered_items: list[NewsItem] = [i for i in items if i is not None]

            _hn_cache = {"items": filtered_items, "timestamp": time.time()}
            return filtered_items

    except Exception as e:
        logger.warning("HN fetch error: %s", e)
        if _hn_cache["items"]:
            return _hn_cache["items"]  # type: ignore[no-any-return]
        return []


async def fetch_rss(source: dict[str, Any]) -> list[NewsItem]:
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        response = await asyncio.to_thread(requests.get, source["feed_url"], headers=headers, timeout=10)

        if response.status_code != 200:
            logger.warning("RSS fetch failed for %s: Status %s", source["name"], response.status_code)
            return []

        feed = feedparser.parse(response.content)

        if hasattr(feed, "bozo_exception") and feed.bozo_exception:
            logger.warning("RSS Parse Warning for %s: %s", source["name"], feed.bozo_exception)

        items: list[NewsItem] = []
        for entry in feed.entries[:30]:
            ts = datetime.now(tz=UTC).isoformat()
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                ts = datetime(*entry.published_parsed[:6]).replace(tzinfo=UTC).isoformat()
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                ts = datetime(*entry.updated_parsed[:6]).replace(tzinfo=UTC).isoformat()

            items.append(
                NewsItem(
                    id=f"{source['id']}_{entry.get('id', entry.link)}",
                    title=entry.title,
                    url=entry.link,
                    source_name=source["name"],
                    timestamp=ts,
                    summary=entry.get("summary", "")[:200],
                )
            )
        return items
    except Exception as e:
        logger.warning("RSS fetch error for %s: %s", source["name"], e)
        return []


@router.get("/feed")
async def get_feed(source_id: str | None = None) -> dict[str, Any]:
    news_settings = get_news_settings()
    sources: list[dict[str, Any]] = news_settings["sources"]

    if source_id:
        sources = [s for s in sources if s["id"] == source_id]

    all_items: list[NewsItem] = []
    tasks: list[Any] = []

    for source in sources:
        if not source.get("enabled", True):
            continue

        if source["id"] == "hn":
            tasks.append(fetch_hn())
        elif source["type"] == "rss" and source.get("feed_url"):
            tasks.append(fetch_rss(source))

    results = await asyncio.gather(*tasks)
    for res in results:
        all_items.extend(res)

    all_items.sort(key=lambda x: x.timestamp, reverse=True)

    return {"status": "success", "items": all_items[:100]}


@router.get("/article")
async def get_article_content(url: str) -> dict[str, Any]:
    """Fetch and render a full webpage using Playwright."""
    _validate_url(url)
    try:
        is_pdf = url.lower().endswith(".pdf") or "arxiv.org/pdf/" in url

        if not is_pdf:
            try:
                head = _safe_request("HEAD", url, timeout=2)
                if "application/pdf" in head.headers.get("Content-Type", "").lower():
                    is_pdf = True
            except Exception:
                pass

        if is_pdf:
            try:
                import pymupdf

                response = _safe_request("GET", url, timeout=15)
                doc = pymupdf.open(stream=response.content, filetype="pdf")

                pdf_title = doc.metadata.get("title", "") if doc.metadata else ""
                if not pdf_title:
                    first_page_text = doc[0].get_text() if len(doc) > 0 else ""
                    first_line = first_page_text.split("\n")[0].strip() if first_page_text else ""
                    pdf_title = first_line[:100] if first_line else url.split("/")[-1]

                html_content = "<div style='padding: 20px; font-family: sans-serif;'>"
                for i, page in enumerate(doc):
                    if i >= 10:
                        html_content += "<p><em>... (Display limited to first 10 pages) ...</em></p>"
                        break
                    html_content += page.get_text("html")
                    html_content += "<hr style='margin: 20px 0; border: 0; border-top: 1px solid #ccc;'/>"

                html_content += "</div>"
                return {"status": "success", "html": html_content, "url": url, "title": pdf_title}
            except Exception as e:
                logger.warning("PDF processing error for %s: %s", url, e)

        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="networkidle", timeout=15000)
            except Exception:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)

            # Re-validate final URL after redirects (SSRF defense-in-depth)
            _validate_url(page.url)

            page_title = await page.title()
            for _ in range(10):
                current_title = await page.title()

                og_title = await page.get_attribute('meta[property="og:title"]', "content")
                if og_title and len(og_title) > 20:
                    page_title = og_title
                    break

                try:
                    h1_text = await page.inner_text("h1", timeout=500)
                    if h1_text and len(h1_text.strip()) > 20:
                        page_title = h1_text.strip()
                        break
                except Exception:
                    pass

                if current_title and len(current_title) > 30:
                    page_title = current_title
                    break

                await page.wait_for_timeout(500)

            html_content = await page.content()
            await browser.close()

            if "<base" not in html_content.lower():
                base_tag = f'<base href="{html_escape(url, quote=True)}" target="_blank">'
                html_content = html_content.replace("<head>", f"<head>{base_tag}", 1)

            return {"status": "success", "html": html_content, "url": url, "title": page_title}

    except Exception as e:
        logger.error("Playwright rendering error for %s: %s", url, e)
        return {"status": "error", "error": str(e)}


@router.get("/reader")
async def get_reader_content(url: str) -> dict[str, Any]:
    """Extract the main article content as markdown for reader mode."""
    _validate_url(url)
    try:
        is_pdf = url.lower().endswith(".pdf") or "arxiv.org/pdf/" in url
        if not is_pdf:
            try:
                head = _safe_request("HEAD", url, timeout=2)
                if "application/pdf" in head.headers.get("Content-Type", "").lower():
                    is_pdf = True
            except Exception:
                pass

        if is_pdf:
            try:
                import pymupdf
                import pymupdf4llm

                response = _safe_request("GET", url, timeout=15)
                doc = pymupdf.open(stream=response.content, filetype="pdf")
                md_text = pymupdf4llm.to_markdown(doc)
                return {"status": "success", "content": md_text, "url": url}
            except Exception as e:
                logger.warning("PDF Reader error for %s: %s", url, e)

        import trafilatura

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        try:
            resp = _safe_request("GET", url, headers=headers, timeout=10)
            resp.raise_for_status()
            downloaded = resp.text
        except Exception as e:
            logger.warning("Reader fetch failed for %s: %s", url, e)
            return {"status": "error", "error": f"Failed to fetch content: {e!s}"}

        if not downloaded:
            return {"status": "error", "error": "Empty content returned"}

        content = trafilatura.extract(downloaded, include_comments=False, include_tables=True, output_format="markdown")

        if not content:
            content = trafilatura.extract(downloaded, include_comments=False)

        if not content:
            return {"status": "error", "error": "Could not extract article content"}

        return {"status": "success", "content": content, "url": url}
    except Exception as e:
        logger.error("Reader extraction error for %s: %s", url, e)
        return {"status": "error", "error": str(e)}


@router.get("/proxy")
async def proxy_content(url: str) -> StreamingResponse:
    """Proxy content to avoid CORS issues."""
    _validate_url(url)
    try:
        r = await asyncio.to_thread(requests.get, url, stream=True, timeout=30, allow_redirects=False)

        async def iterfile() -> Any:
            it = r.iter_content(chunk_size=8192)
            while True:
                chunk = await asyncio.to_thread(next, it, b"")
                if not chunk:
                    break
                yield chunk

        content_type = r.headers.get("Content-Type", "application/octet-stream")

        return StreamingResponse(iterfile(), media_type=content_type)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Proxy error for %s: %s", url, e)
        raise HTTPException(status_code=500, detail=str(e)) from e
