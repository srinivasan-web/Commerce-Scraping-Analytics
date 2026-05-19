from __future__ import annotations

import argparse
import asyncio
import gc
import logging
import os
import random
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

try:
    import regex as re
except ImportError:
    import re

try:
    import aiofiles  # noqa: F401 - kept available for async backend extensions.
except ImportError:
    aiofiles = None

try:
    import pandas as pd  # noqa: F401 - available for downstream data processing.
except ImportError:
    pd = None

from openpyxl import Workbook
from playwright.async_api import BrowserContext, Page, TimeoutError, async_playwright


BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
LOG_DIR = PROJECT_ROOT / "logs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "amazon_products.xlsx"
LOG_FILE = LOG_DIR / "backend_product_scraper.log"
DEFAULT_URL = "https://www.amazon.in/gp/bestsellers/sports/ref=zg_bs_nav_sports_0"

MAX_WORKERS = int(os.getenv("SCRAPER_WORKERS", "3"))
REQUEST_TIMEOUT_MS = int(os.getenv("REQUEST_TIMEOUT_MS", "45000"))
HEADLESS = os.getenv("HEADLESS", "0") == "1"
RANK_ORDERED_SCRAPE = os.getenv("RANK_ORDERED_SCRAPE", "1") != "0"

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-extensions",
    "--disable-sync",
    "--mute-audio",
    "--no-sandbox",
]

HEADERS = {
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

EXCEL_COLUMNS = [
    "Rank",
    "ASIN",
    "Overall Bought Count",
    "Product Price",
    "Total Revenue",
    "Product Name",
    "Brand Name",
    "Number of Reviews",
    "Rating",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

try:
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
except PermissionError:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
logger = logging.getLogger("backend_product_scraper")


def timestamped_output_path(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.stem}_{timestamp}{path.suffix}")


@dataclass(slots=True)
class ProductSeed:
    rank: int
    name: str
    url: str
    asin: str


@dataclass(slots=True)
class ProductRow:
    rank: int
    product_name: str
    product_price: float
    overall_bought_count: int
    asin: str
    product_url: str
    rating: float
    reviews_count: int
    availability: str
    brand: str
    total_revenue: float


class StreamingExcelExporter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.workbook = Workbook(write_only=True)
        self.sheet = self.workbook.create_sheet("Amazon Products")
        self.sheet.append(EXCEL_COLUMNS)
        self.rows_written = 0

    def append(self, row: ProductRow) -> None:
        self.sheet.append(
            [
                row.rank,
                row.asin,
                row.overall_bought_count,
                row.product_price,
                row.total_revenue,
                row.product_name,
                row.brand,
                row.reviews_count,
                row.rating,
            ]
        )
        self.rows_written += 1
        print("[INFO] Excel Row Exported")

    def save(self) -> Path:
        try:
            self.workbook.save(self.path)
            return self.path
        except PermissionError:
            fallback_path = timestamped_output_path(self.path)
            print(f"[WARN] Output file locked: {self.path}")
            print(f"[INFO] Saving Excel to fallback file: {fallback_path}")
            self.workbook.save(fallback_path)
            return fallback_path


def install_uvloop_if_available() -> None:
    if sys.platform == "win32":
        return
    try:
        import uvloop

        uvloop.install()
    except ImportError:
        return


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_price(value: Any) -> float:
    match = re.search(r"[\d,]+(?:\.\d+)?", clean_text(value))
    return float(match.group(0).replace(",", "")) if match else 0.0


def parse_int(value: Any) -> int:
    match = re.search(r"\d[\d,]*", clean_text(value))
    return int(match.group(0).replace(",", "")) if match else 0


def parse_rating(value: Any) -> float:
    match = re.search(r"([0-5](?:\.\d+)?)", clean_text(value))
    return float(match.group(1)) if match else 0.0


def parse_bought_count(value: Any) -> int:
    text = clean_text(value).lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*([km]?)\+?\s*bought", text)
    if not match:
        match = re.search(r"(\d+(?:\.\d+)?)\s*([km]?)\+?", text)
    if not match:
        return 0
    number = float(match.group(1))
    suffix = match.group(2)
    if suffix == "k":
        number *= 1_000
    elif suffix == "m":
        number *= 1_000_000
    return int(number)


def extract_asin(value: str) -> str:
    match = re.search(r"(?:/dp/|/gp/product/|asin=)([A-Z0-9]{10})", value or "")
    return match.group(1) if match else ""


def marketplace_base(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return "https://www.amazon.in"


def normalize_product_url(href: str, base_url: str) -> str:
    absolute = urljoin(base_url, href or "")
    asin = extract_asin(absolute)
    return f"{base_url}/dp/{asin}" if asin else absolute.split("?")[0]


def validate_amazon_url(url: str) -> str:
    parsed = urlparse(clean_text(url))
    if parsed.scheme not in {"http", "https"} or "amazon." not in parsed.netloc:
        raise ValueError("Please enter a valid Amazon URL.")
    return url


async def block_unneeded_resources(route) -> None:
    request = route.request
    url = request.url.lower()
    blocked_types = {"image", "media", "font", "stylesheet"}
    blocked_hosts = ("doubleclick", "googletagmanager", "google-analytics", "facebook", "adsystem")
    if request.resource_type in blocked_types or any(host in url for host in blocked_hosts):
        await route.abort()
        return
    await route.continue_()


async def create_context(browser, base_url: str) -> BrowserContext:
    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": 1366, "height": 850},
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        extra_http_headers=HEADERS,
        base_url=base_url,
    )
    await context.route("**/*", block_unneeded_resources)
    return context


async def light_human_motion(page: Page) -> None:
    await page.mouse.move(random.randint(180, 900), random.randint(180, 650), steps=8)
    await asyncio.sleep(random.uniform(0.06, 0.16))


async def detect_captcha(page: Page) -> bool:
    try:
        text = (await page.locator("body").inner_text(timeout=3000)).lower()
    except Exception:
        return False
    signals = ("robot check", "captcha", "enter the characters you see below")
    return any(signal in text for signal in signals)


async def goto_fast(page: Page, url: str) -> None:
    await page.goto(url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT_MS)
    if await detect_captcha(page):
        raise RuntimeError("Amazon CAPTCHA or robot-check page detected.")


async def smart_scroll_until_products(page: Page, wanted_count: int) -> None:
    selector = (
        "[data-asin] a[href*='/dp/'], [data-asin] a[href*='/gp/product/'], "
        "li[id] a[href*='/dp/'], li[id] a[href*='/gp/product/'], "
        "div.p13n-sc-uncoverable-faceout a[href*='/dp/'], "
        "div.p13n-sc-uncoverable-faceout a[href*='/gp/product/']"
    )
    previous_count = -1
    stable_rounds = 0

    for attempt in range(24):
        count = await page.locator(selector).count()
        if count >= wanted_count:
            return
        if count == previous_count:
            stable_rounds += 1
        else:
            stable_rounds = 0
        if stable_rounds >= 5:
            return
        previous_count = count
        await light_human_motion(page)
        await page.mouse.wheel(0, random.randint(900, 1700))
        if attempt % 4 == 3:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(random.uniform(0.15, 0.35))


async def extract_product_seeds(page: Page, start_url: str, wanted_count: int) -> list[ProductSeed]:
    base_url = marketplace_base(start_url)
    await page.wait_for_selector("body", timeout=REQUEST_TIMEOUT_MS)
    await smart_scroll_until_products(page, wanted_count)

    raw_items = await page.evaluate(
        """
        ({ baseUrl }) => {
            const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
            const asinPattern = /^[A-Z0-9]{10}$/;
            const asinFromUrl = (value) => clean(((value || "").match(/\\/(?:dp|gp\\/product)\\/([A-Z0-9]{10})/) || [])[1] || "");
            const cards = Array.from(document.querySelectorAll([
                "div[data-asin]",
                "li[data-asin]",
                "li[id]",
                "div.p13n-sc-uncoverable-faceout"
            ].join(",")));
            const rows = [];
            const seen = new Set();
            const pushRow = ({ rankText, name, href, asin }) => {
                if (!asin || seen.has(asin)) return;
                seen.add(asin);
                rows.push({ rankText, name, href, asin });
            };

            for (const card of cards) {
                const link = card.querySelector("a[href*='/dp/'], a[href*='/gp/product/']");
                const href = link?.getAttribute("href") || "";
                if (!href) continue;
                const absoluteHref = new URL(href, baseUrl).href;
                const rawId = clean(card.getAttribute("data-asin") || card.getAttribute("id") || "");
                const asin = asinPattern.test(rawId) ? rawId : asinFromUrl(absoluteHref);
                if (!asin) continue;

                const rankText = clean(card.querySelector(".zg-bdg-text, [class*='zg-bdg-text']")?.textContent);
                const name =
                    clean(card.querySelector("img[alt]")?.getAttribute("alt")) ||
                    clean(card.querySelector("div[class*='line-clamp'], .p13n-sc-truncated, a.a-link-normal div")?.textContent);

                pushRow({
                    rankText,
                    name,
                    href: absoluteHref,
                    asin
                });
            }

            for (const list of document.querySelectorAll("[data-client-recs-list]")) {
                try {
                    const records = JSON.parse(list.getAttribute("data-client-recs-list") || "[]");
                    for (const record of records) {
                        const asin = clean(record?.id);
                        if (!asinPattern.test(asin)) continue;
                        const rank = clean(record?.metadataMap?.["render.zg.rank"]);
                        pushRow({
                            rankText: rank ? `#${rank}` : "",
                            name: "",
                            href: new URL(`/dp/${asin}`, baseUrl).href,
                            asin
                        });
                    }
                } catch (error) {
                    // Ignore malformed recommendation metadata and keep DOM cards.
                }
            }
            return rows;
        }
        """,
        {"baseUrl": base_url},
    )

    seeds: list[ProductSeed] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_items, start=1):
        url = normalize_product_url(item.get("href", ""), base_url)
        asin = clean_text(item.get("asin")) or extract_asin(url)
        key = asin or url
        if not key or key in seen:
            continue
        seen.add(key)
        seeds.append(
            ProductSeed(
                rank=parse_int(item.get("rankText")) or index,
                name=clean_text(item.get("name")),
                url=url,
                asin=asin,
            )
        )

    seeds.sort(key=lambda seed: seed.rank)
    seeds = seeds[:wanted_count]
    print(f"[INFO] Products Found: {len(seeds)}")
    if seeds:
        print(f"[INFO] Rank Range: {seeds[0].rank} to {seeds[-1].rank}")
    return seeds


async def extract_product_data(page: Page, seed: ProductSeed) -> ProductRow:
    data = await page.evaluate(
        """
        () => {
            const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
            const firstText = (selectors) => {
                for (const selector of selectors) {
                    const element = document.querySelector(selector);
                    const value = clean(element?.innerText || element?.textContent || element?.getAttribute("content"));
                    if (value) return value;
                }
                return "";
            };
            const firstAttr = (selectors, attr) => {
                for (const selector of selectors) {
                    const element = document.querySelector(selector);
                    const value = clean(element?.getAttribute(attr));
                    if (value) return value;
                }
                return "";
            };
            const bodyText = clean(document.body?.innerText || "");
            const boughtMatch = bodyText.match(/(\\d[\\d,.]*\\s*[kKmM]?\\+?)\\s+bought\\s+in\\s+past\\s+month/i);

            return {
                title: firstText(["#productTitle", "h1#title", "h1"]),
                price: firstText([
                    "#corePrice_feature_div .a-price .a-offscreen",
                    ".priceToPay .a-offscreen",
                    "#priceblock_ourprice",
                    "#priceblock_dealprice",
                    ".a-price .a-offscreen"
                ]),
                rating: firstText(["#acrPopover", "span[data-hook='rating-out-of-text']", "i.a-icon-star span"]),
                reviews: firstText(["#acrCustomerReviewText", "#reviewsMedley .a-size-base"]),
                availability: firstText(["#availability", "#outOfStock"]),
                brand: firstText(["#bylineInfo", "a#bylineInfo", "tr.po-brand td:nth-child(2)", ".po-brand .po-break-word"]),
                asin: firstAttr(["input#ASIN", "input[name='ASIN']"], "value"),
                boughtText: boughtMatch ? boughtMatch[1] : ""
            };
        }
        """
    )

    price = parse_price(data.get("price"))
    bought_count = parse_bought_count(data.get("boughtText"))
    title = clean_text(data.get("title")) or seed.name
    brand = clean_text(data.get("brand"))
    brand = brand.replace("Visit the ", "").replace("Brand:", "").replace(" Store", "").strip()
    asin = clean_text(data.get("asin")) or seed.asin or extract_asin(page.url)

    row = ProductRow(
        rank=seed.rank,
        product_name=title,
        product_price=price,
        overall_bought_count=bought_count,
        asin=asin,
        product_url=seed.url,
        rating=parse_rating(data.get("rating")),
        reviews_count=parse_int(data.get("reviews")),
        availability=clean_text(data.get("availability")),
        brand=brand or title.split(" ")[0],
        total_revenue=round(price * bought_count, 2),
    )
    print("[INFO] Revenue Calculated")
    return row


async def product_worker(
    worker_id: int,
    context: BrowserContext,
    queue: asyncio.Queue[ProductSeed | None],
    exporter: StreamingExcelExporter,
    export_lock: asyncio.Lock,
) -> None:
    page = await context.new_page()
    try:
        while True:
            seed = await queue.get()
            if seed is None:
                queue.task_done()
                return
            try:
                await goto_fast(page, seed.url)
                await light_human_motion(page)
                row = await extract_product_data(page, seed)
                async with export_lock:
                    exporter.append(row)
                print(f"[INFO] Product {seed.rank} Scraped")
                logger.info("Product scraped: %s", asdict(row))
            except Exception as exc:
                logger.exception("Worker %s failed for %s: %s", worker_id, seed.url, exc)
                print(f"[WARN] Product {seed.rank} skipped: {exc}")
            finally:
                queue.task_done()
                gc.collect()
    finally:
        await page.close()


async def scrape_products(start_url: str, product_count: int, output_path: Path, headless: bool) -> Path:
    start_url = validate_amazon_url(start_url)
    base_url = marketplace_base(start_url)
    exporter = StreamingExcelExporter(output_path)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless, args=LAUNCH_ARGS)
        print("[INFO] Browser Started")
        try:
            context = await create_context(browser, base_url)
            category_page = await context.new_page()
            await goto_fast(category_page, start_url)
            print("[INFO] Category Loaded")
            seeds = await extract_product_seeds(category_page, start_url, product_count)
            await category_page.close()

            queue: asyncio.Queue[ProductSeed | None] = asyncio.Queue()
            export_lock = asyncio.Lock()
            seeds.sort(key=lambda seed: seed.rank)
            for seed in seeds:
                await queue.put(seed)

            worker_count = 1 if RANK_ORDERED_SCRAPE else min(MAX_WORKERS, max(len(seeds), 1))
            if RANK_ORDERED_SCRAPE:
                print("[INFO] Rank Ordered Mode: enabled")
            workers = [
                asyncio.create_task(product_worker(index + 1, context, queue, exporter, export_lock))
                for index in range(worker_count)
            ]
            for _ in workers:
                await queue.put(None)

            await queue.join()
            await asyncio.gather(*workers)
            await context.close()
        finally:
            await browser.close()

    path = exporter.save()
    print("[INFO] Scraping Completed")
    return path


def prompt_value(label: str, default: str = "") -> str:
    value = input(f"{label}\n").strip()
    return value or default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backend-only Amazon live product scraper.")
    parser.add_argument("--url", help="Amazon category or product-list URL.")
    parser.add_argument("--count", type=int, help="Number of products to scrape.")
    parser.add_argument("--output", default=str(OUTPUT_FILE), help="Excel output path.")
    parser.add_argument("--headless", action="store_true", default=HEADLESS, help="Run Chromium headless.")
    parser.add_argument("--server", action="store_true", help="Start the FastAPI backend instead of terminal scraping.")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--reload", action="store_true", default=os.getenv("RELOAD", "1") != "0")
    return parser.parse_args()


def run_server(args: argparse.Namespace) -> None:
    import uvicorn

    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


async def run_cli(args: argparse.Namespace) -> None:
    url = args.url or prompt_value("Enter Amazon URL:", DEFAULT_URL)
    count_text = str(args.count) if args.count else prompt_value("Enter Number of Products:", "20")
    product_count = max(1, int(count_text))
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    path = await scrape_products(url, product_count, output_path, args.headless)
    print(f"[INFO] Excel Saved: {path}")


def main() -> None:
    install_uvloop_if_available()
    args = parse_args()
    if args.server:
        run_server(args)
        return
    asyncio.run(run_cli(args))


if __name__ == "__main__":
    main()
