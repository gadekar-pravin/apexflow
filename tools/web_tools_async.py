"""Web scraping tools -- v2 with lazy Playwright import.

Changes from v1:
- Removed sys.stderr print override
- Made playwright import lazy (try/except at module level, raise at call time)
- Replaced print() with logger
"""

from __future__ import annotations

import asyncio
import logging
import random
from pathlib import Path
from typing import Any

import httpx
import trafilatura
from bs4 import BeautifulSoup
from readability import Document

logger = logging.getLogger(__name__)

# Lazy playwright import
_async_playwright: Any = None
_PlaywrightTimeoutError: type[Exception] | None = None
try:
    from playwright.async_api import TimeoutError as _PwTimeout
    from playwright.async_api import async_playwright as _pw

    _async_playwright = _pw
    _PlaywrightTimeoutError = _PwTimeout
except ImportError:
    pass

DIFFICULT_WEBSITES_PATH = Path(__file__).parent / "difficult_websites.txt"


def _require_playwright() -> None:
    """Raise ImportError if playwright is not available."""
    if _async_playwright is None:
        raise ImportError(
            "playwright is required for browser-based scraping. "
            "Install with: pip install playwright && playwright install chromium"
        )


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


def is_difficult_website(url: str) -> bool:
    if not DIFFICULT_WEBSITES_PATH.exists():
        return False
    try:
        with open(DIFFICULT_WEBSITES_PATH, encoding="utf-8") as f:
            difficult_sites = [line.strip().lower() for line in f if line.strip()]
        return any(domain in url.lower() for domain in difficult_sites)
    except Exception as e:
        logger.warning("Failed to read difficult_websites.txt: %s", e)
        return False


def ascii_only(text: str) -> str:
    return text.encode("ascii", errors="ignore").decode()


def choose_best_text(visible: str, main: str, trafilatura_: str) -> tuple[str, str]:
    scores: dict[str, int] = {
        "visible": len(visible.strip()),
        "main": len(main.strip()),
        "trafilatura": len(trafilatura_.strip()),
    }
    best = max(scores, key=lambda k: scores[k])
    return {"visible": visible, "main": main, "trafilatura": trafilatura_}[best], best


async def web_tool_playwright(url: str, max_total_wait: int = 15) -> dict[str, str]:
    _require_playwright()
    result: dict[str, str] = {"url": url}

    try:
        async with _async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(url, wait_until="domcontentloaded", timeout=15000)

            try:
                await page.wait_for_function(
                    """() => {
                        const body = document.querySelector('body');
                        return body && (body.innerText || "").length > 1000;
                    }""",
                    timeout=15000,
                )
            except Exception as e:
                logger.warning("Generic wait failed: %s", e)

            await asyncio.sleep(5)

            try:
                await page.evaluate(
                    """() => {
                    window.stop();
                    document.querySelectorAll('script').forEach(s => s.remove());
                }"""
                )
            except Exception as e:
                logger.warning("JS stop failed: %s", e)

            html = await page.content()
            visible_text = await page.inner_text("body")
            title = await page.title()
            await browser.close()

            try:
                main_text: str = await asyncio.to_thread(
                    lambda: BeautifulSoup(Document(html).summary(), "html.parser").get_text(separator="\n", strip=True)
                )
            except Exception as e:
                logger.warning("Readability failed: %s", e)
                main_text = ""

            try:
                trafilatura_text: str = await asyncio.to_thread(lambda: trafilatura.extract(html) or "")
            except Exception as e:
                logger.warning("Trafilatura failed: %s", e)
                trafilatura_text = ""

            best_text, source = choose_best_text(visible_text, main_text, trafilatura_text)

            result.update(
                {
                    "title": title,
                    "html": html,
                    "text": visible_text,
                    "main_text": main_text,
                    "trafilatura_text": trafilatura_text,
                    "best_text": ascii_only(best_text),
                    "best_text_source": source,
                }
            )

    except Exception as e:
        if _PlaywrightTimeoutError and isinstance(e, _PlaywrightTimeoutError):
            result.update(
                {
                    "title": "[timeout: goto]",
                    "html": "",
                    "text": "[timed out]",
                    "main_text": "[no HTML extracted]",
                    "trafilatura_text": "",
                    "best_text": "[no text]",
                    "best_text_source": "timeout",
                }
            )
        else:
            logger.error("Playwright error: %s", e, exc_info=True)
            result.update(
                {
                    "title": "[error]",
                    "html": "",
                    "text": f"[error: {e}]",
                    "main_text": "[no HTML extracted]",
                    "trafilatura_text": "",
                    "best_text": "[no text]",
                    "best_text_source": "error",
                }
            )

    return result


_MAX_REDIRECTS = 10


async def _fetch_with_ssrf_check(
    url: str,
    headers: dict[str, str],
    timeout: int,
    ssrf_validator: Any,
) -> httpx.Response:
    """Follow redirects manually, re-validating each hop against SSRF rules."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for _ in range(_MAX_REDIRECTS):
            response = await client.get(url, headers=headers)
            if response.is_redirect:
                location = response.headers.get("location", "")
                if not location:
                    break
                url = str(response.url.join(location))
                ssrf_validator(url)  # raises ValueError if blocked
                continue
            return response
    return response


async def smart_web_extract(
    url: str,
    timeout: int = 5,
    ssrf_validator: Any | None = None,
) -> dict[str, str]:
    headers = get_random_headers()

    try:
        if is_difficult_website(url):
            logger.info("Detected difficult site (%s) -> skipping fast scrape", url)
            return await web_tool_playwright(url)

        if ssrf_validator:
            # Manual redirect following with SSRF re-validation
            response = await _fetch_with_ssrf_check(url, headers, timeout, ssrf_validator)
        else:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)

        html = response.content.decode("utf-8", errors="replace")

        doc = Document(html)
        main_html = doc.summary()
        main_text = BeautifulSoup(main_html, "html.parser").get_text(separator="\n", strip=True)
        visible_text = BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)
        trafilatura_text = trafilatura.extract(html) or ""
        best_text, best_source = choose_best_text(visible_text, main_text, trafilatura_text)

        if len(best_text) >= 300:
            return {
                "url": url,
                "title": Document(html).short_title(),
                "html": html,
                "text": visible_text,
                "main_text": main_text,
                "trafilatura_text": trafilatura_text,
                "best_text": ascii_only(best_text),
                "best_text_source": best_source,
            }

        logger.info("Fast scrape too small, falling back to playwright...")

    except Exception as e:
        logger.warning("Fast scrape failed: %s", e)

    return await web_tool_playwright(url)
