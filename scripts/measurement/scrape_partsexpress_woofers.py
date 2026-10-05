"""Download the complete Parts Express Woofer category with product specifications.

Output includes every catalog product and adds T/S, enclosure, resource, and
physical-specification tables when they are published on the product page.
"""

from __future__ import annotations

import asyncio
import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from scripts.project_paths import CATALOG_DIR

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright


DEFAULT_CATEGORY_URL = (
    "https://www.parts-express.com/speaker-components/"
    "hi-fi-woofers-subwoofers-midranges-tweeters/woofers"
)
DEFAULT_EXPECTED_CATALOG_COUNT = 404
DEFAULT_PAGE_COUNT = 9
REQUEST_TIMEOUT_SECONDS = 30
WORKERS = 8

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/132.0 Safari/537.36"
        )
    }
)


def get_html(url: str) -> str:
    """Fetch a page with limited retries for transient storefront failures."""
    for attempt in range(3):
        try:
            response = SESSION.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    raise RuntimeError("Unreachable")


def catalog_urls(category_url: str, page_count: int, expected_count: int) -> list[str]:
    """Collect product links from the JavaScript-rendered category pages."""
    product_urls: dict[str, None] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2}", lambda route: route.abort())
        for page_number in range(1, page_count + 1):
            page.goto(f"{category_url}?page={page_number}&show=48", wait_until="domcontentloaded")
            cards = page.locator('[data-type="item"] a.facets-item-cell-grid-link')
            expected_on_page = min(48, expected_count - (page_number - 1) * 48)
            page.wait_for_function(
                "([selector, count]) => document.querySelectorAll(selector).length >= count",
                arg=['[data-type="item"] a.facets-item-cell-grid-link', expected_on_page],
            )
            urls = cards.evaluate_all(
                "links => links.map(link => new URL(link.getAttribute('href'), location.origin).href)"
            )
            for url in urls:
                product_urls[url.split("?", 1)[0]] = None
        browser.close()
    return sorted(product_urls)


def table_data(table: object) -> tuple[str, dict[str, str]] | None:
    header = table.select_one("th h4, th")
    if not header:
        return None
    section = header.get_text(" ", strip=True)
    values: dict[str, str] = {}
    for row in table.select("tr"):
        cells = row.select("td")
        if len(cells) >= 2:
            key = cells[0].get_text(" ", strip=True)
            value = cells[1].get_text(" ", strip=True)
            if key and value:
                values[key] = value
    return (section, values) if section and values else None


def parse_product_html(url: str, html: str) -> dict[str, object]:
    """Parse one rendered product document while preserving published specs."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("h1")
    product: dict[str, object] = {
        "url": url,
        "title": title.get_text(" ", strip=True) if title else None,
    }

    brand = soup.select_one('a[href^="/brand/"]')
    if brand:
        product["brand"] = brand.get_text(" ", strip=True)

    body_text = soup.get_text(" ", strip=True)
    price = re.search(r"Your Price:\s*\$([\d.]+)", body_text, re.IGNORECASE)
    if price:
        product["price_usd"] = float(price.group(1))

    for table in soup.select("table"):
        parsed = table_data(table)
        if parsed:
            section, values = parsed
            product[section] = values

    resources = []
    seen_resources: set[str] = set()
    for link in soup.select('a[href$=".pdf" i], a[href$=".zip" i]'):
        resource_url = link.get("href")
        if not resource_url:
            continue
        resource_url = requests.compat.urljoin(url, resource_url)
        if resource_url in seen_resources:
            continue
        seen_resources.add(resource_url)
        resources.append(
            {"name": link.get_text(" ", strip=True), "url": resource_url}
        )
    product["manuals_and_resources"] = resources
    product["has_thiele_small_parameters"] = "Thiele-Small Parameters" in product
    return product


async def browser_product_data(
    urls: list[str], workers: int
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    """Render product pages concurrently to obtain the storefront's full DOM."""
    products: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    semaphore = asyncio.Semaphore(workers)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2}",
            lambda route: route.abort(),
        )

        async def fetch_product(url: str) -> dict[str, object]:
            async with semaphore:
                for attempt in range(3):
                    page = await context.new_page()
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        await page.wait_for_selector("h1", timeout=15000)
                        await page.wait_for_selector("table", timeout=15000)
                        return parse_product_html(url, await page.content())
                    except Exception:
                        if attempt == 2:
                            raise
                        await asyncio.sleep(attempt + 1)
                    finally:
                        await page.close()

        async def fetch_with_error(url: str) -> tuple[str, dict[str, object] | None, str | None]:
            try:
                return url, await fetch_product(url), None
            except Exception as error:
                return url, None, str(error)

        tasks = [asyncio.create_task(fetch_with_error(url)) for url in urls]
        for index, task in enumerate(asyncio.as_completed(tasks), start=1):
            url, product, error = await task
            if product is not None:
                products.append(product)
            else:
                failures.append({"url": url, "error": error or "Unknown error"})
            print(f"Processed {index}/{len(urls)}")
        await browser.close()
    return products, failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category-url", default=DEFAULT_CATEGORY_URL)
    parser.add_argument("--expected-count", type=int, default=DEFAULT_EXPECTED_CATALOG_COUNT)
    parser.add_argument("--page-count", type=int, default=DEFAULT_PAGE_COUNT)
    parser.add_argument("--workers", type=int, default=WORKERS)
    parser.add_argument(
        "--output",
        type=Path,
        default=CATALOG_DIR / "partsexpress_404_woofers_with_ts_params.json",
    )
    arguments = parser.parse_args()

    urls = catalog_urls(
        arguments.category_url, arguments.page_count, arguments.expected_count
    )
    print(f"Found {len(urls)} unique product URLs (storefront reports {arguments.expected_count}).")

    products, failures = asyncio.run(browser_product_data(urls, arguments.workers))

    products.sort(key=lambda product: str(product.get("title") or ""))
    ts_count = sum(product["has_thiele_small_parameters"] for product in products)
    output = {
        "source": arguments.category_url,
        "scraped_at_utc": datetime.now(timezone.utc).isoformat(),
        "catalog_products_reported_by_storefront": arguments.expected_count,
        "catalog_products_downloaded": len(products),
        "products_with_thiele_small_parameters": ts_count,
        "currency": "USD",
        "products": products,
        "failures": failures,
    }
    arguments.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(products)} products, {ts_count} with T/S parameters, to {arguments.output}")
    if failures:
        print(f"Failed pages: {len(failures)} (listed in the JSON output)")


if __name__ == "__main__":
    main()