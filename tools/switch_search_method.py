"""Multi-engine web search -- v2 with lazy Playwright import.

Changes from v1:
- Removed sys.stderr print override
- Made playwright import lazy
- Replaced print() with logger
"""

from __future__ import annotations

import asyncio
import logging
import random
import urllib.parse
from datetime import datetime, timedelta
from typing import Any

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Lazy playwright import
_async_playwright: Any = None
try:
    from playwright.async_api import async_playwright as _pw

    _async_playwright = _pw
except ImportError:
    pass

SEARCH_ENGINES = [
    "duck_http",
    "duck_playwright",
    "bing_playwright",
    "yahoo_playwright",
    "ecosia_playwright",
    "mojeek_playwright",
]


def _require_playwright() -> None:
    if _async_playwright is None:
        raise ImportError(
            "playwright is required for browser-based search. "
            "Install with: pip install playwright && playwright install chromium"
        )


class RateLimiter:
    def __init__(self, cooldown_seconds: int = 2) -> None:
        self.cooldown = timedelta(seconds=cooldown_seconds)
        self.last_called: dict[str, datetime] = {}

    async def acquire(self, key: str) -> None:
        now = datetime.now()
        last = self.last_called.get(key)
        if last and (now - last) < self.cooldown:
            wait = (self.cooldown - (now - last)).total_seconds()
            logger.debug("Rate limiting %s, sleeping for %.1fs", key, wait)
            await asyncio.sleep(wait)
        self.last_called[key] = now


rate_limiter = RateLimiter(cooldown_seconds=2)


def get_random_headers() -> dict[str, str]:
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 Chrome/113.0.5672.92 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_2) AppleWebKit/605.1.15 Version/16.3 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        "Mozilla/5.0 (Linux; Android 13; Pixel 6) AppleWebKit/537.36 Chrome/117.0.5938.132 Mobile Safari/537.36",
        (
            "Mozilla/5.0 (Linux; Android 13; SAMSUNG SM-G998B) AppleWebKit/537.36"
            " Chrome/92.0.4515.159 Mobile Safari/537.36 SamsungBrowser/15.0"
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
            " Version/17.0 Mobile Safari/604.1"
        ),
        "Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 Version/16.6 Mobile Safari/604.1",
    ]
    return {"User-Agent": random.choice(user_agents)}


async def use_duckduckgo_http(query: str) -> list[str]:
    await rate_limiter.acquire("duck_http")
    url = "https://html.duckduckgo.com/html"
    headers = get_random_headers()
    data = {"q": query}

    async with httpx.AsyncClient() as client:
        r = await client.post(url, data=data, headers=headers, timeout=30.0)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        links: list[str] = []

        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            if not href:
                continue
            if not isinstance(href, str):
                continue
            if "uddg=" in href:
                parts = href.split("uddg=")
                if len(parts) > 1:
                    href = urllib.parse.unquote(parts[1].split("&")[0])
            if href.startswith("http") and href not in links:
                links.append(href)

        if not links:
            logger.info("[duck_http] No links found in results")

        return links


async def use_playwright_search(query: str, engine: str) -> list[str]:
    _require_playwright()
    await rate_limiter.acquire(engine)
    urls: list[str] = []
    async with _async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            engine_url_map = {
                "duck_playwright": "https://html.duckduckgo.com/html",
                "bing_playwright": "https://www.bing.com/search",
                "yahoo_playwright": "https://search.yahoo.com/search",
                "ecosia_playwright": "https://www.ecosia.org/search",
                "mojeek_playwright": "https://www.mojeek.com/search",
            }

            search_url = f"{engine_url_map[engine]}?q={query.replace(' ', '+')}"
            logger.info("Navigating to %s", search_url)
            await page.goto(search_url)
            await asyncio.sleep(3)

            if engine == "duck_playwright":
                await page.wait_for_selector("a.result__a", timeout=10000)
                results = await page.query_selector_all("a.result__a")
            elif engine == "bing_playwright":
                results = await page.query_selector_all("li.b_algo h2 a")
            elif engine == "yahoo_playwright":
                results = await page.query_selector_all("div.compTitle h3.title a")
            elif engine == "ecosia_playwright":
                await page.wait_for_selector("a.result__link", timeout=10000)
                results = await page.query_selector_all("a.result__link")
            elif engine == "mojeek_playwright":
                await page.wait_for_selector("a.title", timeout=10000)
                results = await page.query_selector_all("a.title")
            else:
                logger.warning("Unknown engine: %s", engine)
                return []

            if not results:
                logger.info("[%s] No URLs found, possibly blocked. Retrying...", engine)
                await asyncio.sleep(5)
                if engine == "duck_playwright":
                    results = await page.query_selector_all("a.result__a")
                elif engine == "bing_playwright":
                    results = await page.query_selector_all("li.b_algo h2 a")
                elif engine == "yahoo_playwright":
                    results = await page.query_selector_all("div.compTitle h3.title a")
                elif engine == "ecosia_playwright":
                    results = await page.query_selector_all("a.result__link")
                elif engine == "mojeek_playwright":
                    results = await page.query_selector_all("div.result_title a")

            for r in results:
                try:
                    href = await r.get_attribute("href")
                    if not href:
                        continue
                    if "uddg=" in href:
                        parts = href.split("uddg=")
                        if len(parts) > 1:
                            href = urllib.parse.unquote(parts[1].split("&")[0])
                    if href.startswith("http") and href not in urls:
                        urls.append(href)
                except Exception as e:
                    logger.debug("Skipped a bad link: %s", e)
        except Exception as e:
            logger.error("Error while processing %s: %s", engine, e)
        finally:
            await browser.close()

    if not urls:
        logger.info("Still no URLs found for %s after retry.", engine)

    return urls


async def smart_search(query: str, limit: int = 5) -> list[str]:
    for engine in SEARCH_ENGINES:
        logger.info("Trying engine: %s", engine)
        try:
            if engine == "duck_http":
                results = await use_duckduckgo_http(query)
            else:
                results = await use_playwright_search(query, engine)
            if results:
                return results[:limit]
            else:
                logger.info("No results from %s. Trying next...", engine)
        except Exception as e:
            logger.warning("Engine %s failed: %s. Trying next...", engine, e)

    logger.warning("All engines failed.")
    return []
