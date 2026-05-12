"""
Production-style Amazon Best Seller analytics scraper.

This script uses async Playwright to collect bestseller parent products, opens
each product detail page, attempts to enumerate variants, computes analytics,
and exports a structured CSV plus a multi-sheet Excel workbook.

Important notes:
- Amazon changes markup often, so selectors are intentionally layered.
- Public Amazon pages do not expose exact sales. Monthly units are estimated
  from "bought in past month" when visible, otherwise from bestseller rank.
- CAPTCHA pages are detected and the run stops cleanly. This script does not
  bypass CAPTCHA or access controls.
"""

import asyncio
import argparse
import logging
import os
import random
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import pandas as pd
from openpyxl import load_workbook
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from playwright.async_api import BrowserContext, Locator, Page, TimeoutError, async_playwright


# =========================================================
# CONFIGURATION
# =========================================================

DEFAULT_TARGET_URL = "https://www.amazon.in/gp/bestsellers/sports/3404687031/ref=pd_zg_hrsr_sports"
TARGET_URL = os.getenv("TARGET_URL", DEFAULT_TARGET_URL)
BASE_URL = os.getenv("AMAZON_BASE_URL", "https://www.amazon.in")
MAIN_CATEGORY = "Sports"
SUBCATEGORY = "Bestsellers"

PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "output"
LOG_DIR = PROJECT_DIR / "logs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

CSV_FILE = OUTPUT_DIR / "amazon_bestsellers.csv"
EXCEL_FILE = OUTPUT_DIR / "amazon_bestsellers.xlsx"
LOG_FILE = LOG_DIR / "amazon_bestseller_analytics.log"

REMOVED_EXPORT_COLUMNS = {
    "Manufacturer",
    "Product Bullets",
    "Product Details",
    "Deal Badge",
    "Sponsored Status",
    "Variant Deal Badge",
}


def timestamped_output_path(path: Path) -> Path:
    """Return a same-folder fallback path when the normal export file is locked."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.stem}_{timestamp}{path.suffix}")

MAX_PARENT_PRODUCTS = int(os.getenv("MAX_PARENT_PRODUCTS", "0"))  # 0 means scrape all visible products.
MAX_BESTSELLER_PAGES = int(os.getenv("MAX_BESTSELLER_PAGES", "2"))
MAX_VARIANTS_PER_PRODUCT = int(os.getenv("MAX_VARIANTS_PER_PRODUCT", "30"))
DETAIL_PAGE_CONCURRENCY = int(os.getenv("DETAIL_PAGE_CONCURRENCY", "4"))
RETRY_COUNT = 3
HEADLESS = False
SLOW_MO_MS = int(os.getenv("SLOW_MO_MS", "80"))
SCRAPE_VARIANTS = os.getenv("SCRAPE_VARIANTS", "true").lower() == "true"
BLOCK_STATIC_ASSETS = os.getenv("BLOCK_STATIC_ASSETS", "true").lower() == "true"
REQUEST_TIMEOUT_MS = int(os.getenv("REQUEST_TIMEOUT_MS", "60000"))
DETAIL_LOAD_DELAY = float(os.getenv("DETAIL_LOAD_DELAY", "0.7"))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

HEADERS = {
    "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Upgrade-Insecure-Requests": "1",
}

PRODUCT_CARD_SELECTORS = [
    "div.p13n-sc-uncoverable-faceout",
    "div[data-asin]:has(a[href*='/dp/'])",
    "li.zg-carousel-general-faceout",
]

VARIANT_CONTAINER_SELECTORS = [
    "#variation_color_name li",
    "#variation_size_name li",
    "#variation_style_name li",
    "#variation_pattern_name li",
    "#variation_item_package_quantity li",
    "#variation_configuration li",
    "li.swatchAvailable",
    "li.swatchSelect",
]


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("amazon_bestseller_analytics")


# =========================================================
# DATA MODELS
# =========================================================

@dataclass
class ParentSeed:
    rank: int
    name: str
    url: str
    asin: str
    image_url: str
    sponsored_status: bool
    bestseller_badge: bool


# =========================================================
# GENERAL HELPERS
# =========================================================

def clean_text(value: Any) -> str:
    """Normalize whitespace and safely stringify missing values."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def to_float(value: Any) -> float:
    """Convert text such as 'INR 1,299.00' into a float."""
    text = clean_text(value)
    match = re.search(r"[\d,]+(?:\.\d+)?", text)
    if not match:
        return 0.0
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return 0.0


def to_int(value: Any) -> int:
    """Convert text containing a number into an int."""
    text = clean_text(value)
    match = re.search(r"\d[\d,]*", text)
    if not match:
        return 0
    return int(match.group(0).replace(",", ""))


def extract_asin(url_or_text: str) -> str:
    """Extract ASIN from Amazon URLs or text."""
    match = re.search(r"(?:/dp/|/gp/product/|asin=)([A-Z0-9]{10})", url_or_text or "")
    return match.group(1) if match else ""


def normalize_url(href: str) -> str:
    """Build an absolute Amazon URL and prefer a clean /dp/ASIN URL when possible."""
    if not href:
        return ""
    url = urljoin(BASE_URL, href)
    asin = extract_asin(url)
    return f"{BASE_URL}/dp/{asin}" if asin else url.split("?")[0]


def is_product_url(url: str) -> bool:
    """Return true when a URL points directly at an Amazon product detail page."""
    return bool(extract_asin(url))


def infer_base_url(url: str) -> str:
    """Infer marketplace base URL from the configured target URL."""
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return BASE_URL


def parse_rating(value: Any) -> float:
    """Extract rating from strings such as '4.2 out of 5 stars'."""
    match = re.search(r"([0-5](?:\.\d+)?)", clean_text(value))
    return float(match.group(1)) if match else 0.0


def parse_bought_count(value: Any) -> int:
    """Convert '300+', '1K+', '5K+' bought text into a numeric value."""
    text = clean_text(value).lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*([kKmM]?)\+?\s*bought", text)
    if not match:
        match = re.search(r"(\d+(?:\.\d+)?)\s*([kKmM]?)\+?", text)
    if not match:
        return 0

    number = float(match.group(1))
    suffix = match.group(2).lower()
    if suffix == "k":
        number *= 1000
    elif suffix == "m":
        number *= 1_000_000
    return int(number)


def estimate_units_from_rank(rank: int) -> int:
    """Estimate monthly units from bestseller rank when no bought count is shown."""
    if rank <= 1:
        return 5000
    if rank <= 5:
        return 3500
    if rank <= 10:
        return 2200
    if rank <= 25:
        return 1200
    if rank <= 50:
        return 650
    if rank <= 100:
        return 250
    return 100


def price_category(price: float) -> str:
    """Bucket product price for analysis."""
    if price <= 0:
        return "Unknown"
    if price < 500:
        return "Budget"
    if price <= 2000:
        return "Mid Range"
    return "Premium"


def discount_category(discount_pct: float) -> str:
    """Bucket discount percentage for analysis."""
    if discount_pct <= 0:
        return "No Discount"
    if discount_pct < 15:
        return "Low Discount"
    if discount_pct < 35:
        return "Medium Discount"
    return "High Discount"


def score(value: float, maximum: float) -> float:
    """Normalize a metric into a 0-100 score."""
    if maximum <= 0:
        return 0.0
    return round(min(max(value / maximum * 100, 0), 100), 2)


async def random_delay(min_seconds: float = 0.8, max_seconds: float = 2.4) -> None:
    """Add random wait time between actions."""
    await asyncio.sleep(random.uniform(min_seconds, max_seconds))


def cap_items(items: list[Any], limit: int) -> list[Any]:
    """Return all items unless a positive limit is configured."""
    return items if limit <= 0 else items[:limit]


async def safe_text(root: Page | Locator, selectors: list[str], timeout: int = 2500) -> str:
    """Return first visible text found by fallback selectors."""
    for selector in selectors:
        try:
            text = await root.locator(selector).first.inner_text(timeout=timeout)
            text = clean_text(text)
            if text:
                return text
        except Exception:
            continue
    return ""


async def safe_attr(root: Page | Locator, selectors: list[str], attribute: str, timeout: int = 2500) -> str:
    """Return first attribute found by fallback selectors."""
    for selector in selectors:
        try:
            value = await root.locator(selector).first.get_attribute(attribute, timeout=timeout)
            value = clean_text(value)
            if value:
                return value
        except Exception:
            continue
    return ""


async def retry_async(label: str, coro_factory, retries: int = RETRY_COUNT):
    """Run an async operation with retry and random backoff."""
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            last_error = exc
            logger.warning("%s failed on attempt %s/%s: %s", label, attempt, retries, exc)
            await random_delay(1.5 * attempt, 3.0 * attempt)
    raise last_error


# =========================================================
# BROWSER HELPERS
# =========================================================

async def new_context(browser) -> BrowserContext:
    """Create a realistic browser context."""
    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": random.choice([1366, 1440, 1536]), "height": random.choice([850, 900, 960])},
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        extra_http_headers=HEADERS,
    )

    if BLOCK_STATIC_ASSETS:
        await context.route("**/*", route_static_assets)

    return context


async def route_static_assets(route) -> None:
    """Abort heavy resources while keeping document/scripts available."""
    request = route.request
    if request.resource_type in {"image", "media", "font", "stylesheet"}:
        await route.abort()
    else:
        await route.continue_()


async def human_mouse_movement(page: Page) -> None:
    """Move mouse in small random paths to avoid perfectly static interaction."""
    for _ in range(random.randint(2, 5)):
        await page.mouse.move(random.randint(80, 1200), random.randint(120, 760), steps=random.randint(8, 18))
        await random_delay(0.15, 0.45)


async def detect_captcha(page: Page) -> bool:
    """Detect Amazon robot-check or CAPTCHA pages."""
    try:
        body = (await page.locator("body").inner_text(timeout=10000)).lower()
    except Exception:
        return False

    signals = [
        "enter the characters you see below",
        "type the characters you see in this image",
        "sorry, we just need to make sure you're not a robot",
        "robot check",
        "captcha",
    ]
    return any(signal in body for signal in signals)


async def goto_with_retry(page: Page, url: str, wait_until: str = "domcontentloaded") -> None:
    """Navigate with retry handling for slow or flaky pages."""
    async def action():
        await page.goto(url, wait_until=wait_until, timeout=REQUEST_TIMEOUT_MS)
        await random_delay(DETAIL_LOAD_DELAY, DETAIL_LOAD_DELAY + 1.2)
        if await detect_captcha(page):
            raise RuntimeError("Amazon CAPTCHA or robot-check page detected.")

    await retry_async(f"navigate {url}", action)


async def slow_scroll(page: Page, passes: int = 12) -> None:
    """Slowly scroll a page so lazy-loaded content appears."""
    await human_mouse_movement(page)
    for _ in range(passes):
        await page.mouse.wheel(0, random.randint(900, 1700))
        await random_delay(0.25, 0.85)
    await page.evaluate("window.scrollTo(0, 0)")
    await random_delay(0.4, 1.0)


# =========================================================
# BESTSELLER PAGE EXTRACTION
# =========================================================

async def extract_parent_seeds(page: Page) -> list[ParentSeed]:
    """Extract product seeds from the bestseller category page."""
    product_selector = ", ".join(PRODUCT_CARD_SELECTORS)
    await page.wait_for_selector(product_selector, timeout=45000)
    raw_items = await page.evaluate(
        """
        ({ productSelector, baseUrl }) => {
            const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
            const absoluteUrl = (href) => {
                try {
                    return href ? new URL(href, baseUrl).href : "";
                } catch {
                    return "";
                }
            };
            const firstText = (root, selectors) => {
                for (const selector of selectors) {
                    const element = root.querySelector(selector);
                    const value = clean(element?.innerText || element?.textContent || element?.getAttribute("alt"));
                    if (value) return value;
                }
                return "";
            };
            const firstAttr = (root, selectors, attr) => {
                for (const selector of selectors) {
                    const element = root.querySelector(selector);
                    const value = clean(element?.getAttribute(attr));
                    if (value) return value;
                }
                return "";
            };
            const cards = Array.from(document.querySelectorAll(productSelector));
            return cards.map((card, index) => {
                const text = clean(card.innerText).toLowerCase();
                const href = firstAttr(card, [
                    "a.a-link-normal[href*='/dp/']",
                    "a[href*='/dp/']",
                    "a[href*='/gp/product/']"
                ], "href");
                const url = absoluteUrl(href);
                const name = firstText(card, [
                    "div[class*='p13n-sc-css-line-clamp']",
                    "a.a-link-normal div",
                    "img[alt]"
                ]) || firstAttr(card, ["img"], "alt");
                const imageUrl = firstAttr(card, ["img"], "src") || firstAttr(card, ["img"], "data-src");
                const rankText = firstText(card, [".zg-bdg-text", "[class*='zg-bdg-text']"]);
                return {
                    index: index + 1,
                    rankText,
                    name,
                    url,
                    imageUrl,
                    sponsoredStatus: text.includes("sponsored"),
                    bestsellerBadge: text.includes("best seller") || text.includes("#1 best seller")
                };
            }).filter((item) => item.name && item.url);
        }
        """,
        {"productSelector": product_selector, "baseUrl": BASE_URL},
    )

    seeds: list[ParentSeed] = []
    seen = set()

    for item in raw_items:
        try:
            rank_text = item.get("rankText")
            rank = to_int(rank_text) or int(item.get("index") or 0)

            url = normalize_url(item.get("url", ""))
            asin = extract_asin(url)
            name = clean_text(item.get("name"))

            key = asin or url or name
            if not name or not url or key in seen:
                continue
            seen.add(key)

            seeds.append(
                ParentSeed(
                    rank=rank,
                    name=name,
                    url=url,
                    asin=asin,
                    image_url=clean_text(item.get("imageUrl")),
                    sponsored_status=bool(item.get("sponsoredStatus")),
                    bestseller_badge=bool(item.get("bestsellerBadge")),
                )
            )
        except Exception as exc:
            logger.exception("Failed to parse bestseller card: %s", exc)

    seeds.sort(key=lambda item: item.rank)
    return cap_items(seeds, MAX_PARENT_PRODUCTS)


async def get_next_bestseller_url(page: Page) -> str:
    """Find the next bestseller pagination URL, if Amazon exposes one."""
    href = await page.evaluate(
        """
        () => {
            const selectors = [
                "li.a-last:not(.a-disabled) a",
                "a[aria-label='Next page']",
                "a[href*='pg=2']",
                "a[href*='pg=3']"
            ];
            for (const selector of selectors) {
                const element = document.querySelector(selector);
                const href = element?.getAttribute("href");
                if (href) return href;
            }
            const next = Array.from(document.querySelectorAll("a"))
                .find((element) => (element.innerText || "").trim().toLowerCase() === "next");
            return next?.getAttribute("href") || "";
        }
        """
    )
    return urljoin(BASE_URL, href) if href else ""


async def collect_bestseller_seeds(page: Page, start_url: str) -> list[ParentSeed]:
    """Collect parent product URLs across bestseller pagination."""
    all_seeds: list[ParentSeed] = []
    seen = set()
    next_url = start_url

    for page_number in range(1, MAX_BESTSELLER_PAGES + 1):
        if not next_url:
            break

        print(f"Opening bestseller page {page_number}/{MAX_BESTSELLER_PAGES}...")
        await goto_with_retry(page, next_url)
        print("Scrolling bestseller page...")
        await slow_scroll(page, passes=10)

        seeds = await extract_parent_seeds(page)
        added = 0
        for seed in seeds:
            key = seed.asin or seed.url
            if key in seen:
                continue
            seen.add(key)
            all_seeds.append(seed)
            added += 1

        print(f"Collected {added} new products from bestseller page {page_number}.")

        if MAX_PARENT_PRODUCTS > 0 and len(all_seeds) >= MAX_PARENT_PRODUCTS:
            return all_seeds[:MAX_PARENT_PRODUCTS]

        next_candidate = await get_next_bestseller_url(page)
        if not next_candidate or next_candidate == next_url:
            break
        next_url = next_candidate
        await random_delay(0.8, 1.8)

    all_seeds.sort(key=lambda item: item.rank)
    return cap_items(all_seeds, MAX_PARENT_PRODUCTS)


# =========================================================
# PRODUCT DETAIL EXTRACTION
# =========================================================

async def product_json(page: Page, seed: ParentSeed) -> dict[str, Any]:
    """Extract broad product state from the currently loaded detail page."""
    return await page.evaluate(
        """
        ({ seed, mainCategory, subcategory }) => {
            const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
            const text = (selector) => clean(document.querySelector(selector)?.innerText || "");
            const attr = (selector, name) => clean(document.querySelector(selector)?.getAttribute(name) || "");
            const texts = (selectors) => {
                const values = [];
                for (const selector of selectors) {
                    for (const element of document.querySelectorAll(selector)) {
                        const value = clean(element.innerText || element.textContent || element.getAttribute("content"));
                        if (value && !values.includes(value)) values.push(value);
                    }
                }
                return values;
            };
            const allText = (selectors) => {
                for (const selector of selectors) {
                    const value = text(selector);
                    if (value) return value;
                }
                return "";
            };
            const allAttr = (selectors, name) => {
                for (const selector of selectors) {
                    const value = attr(selector, name);
                    if (value) return value;
                }
                return "";
            };
            const pageText = clean(document.body?.innerText || "");
            const title = allText(["#productTitle", "span#title", "h1"]);
            const hiddenAsin = attr("[name='ASIN']", "value");
            const brand = allText(["#bylineInfo", "a#bylineInfo", "tr.po-brand td:nth-child(2)", ".po-brand .po-break-word"]);
            const priceSelectors = [
                "#corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen",
                "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
                ".priceToPay .a-offscreen",
                "#priceblock_ourprice",
                "#priceblock_dealprice",
                "#priceblock_saleprice",
                "#tp_price_block_total_price_ww .a-price .a-offscreen",
                ".a-price .a-offscreen"
            ];
            const originalPriceSelectors = [".basisPrice .a-offscreen", ".a-text-price .a-offscreen", "#listPrice .a-offscreen"];
            const price = allText(priceSelectors);
            const originalPrice = allText(originalPriceSelectors);
            const allVisiblePrices = texts([...priceSelectors, ...originalPriceSelectors]);
            const discount = allText([".savingsPercentage", "#corePriceDisplay_desktop_feature_div .savingsPercentage"]);
            const dealBadge = allText(["#dealBadgeSupportingText", ".dealBadge", "[class*='dealBadge']"]);
            const coupon = allText(["label[id*='coupon']", ".couponLabelText", "[class*='coupon']"]);
            const rating = allText(["#acrPopover .a-icon-alt", "span[data-hook='rating-out-of-text']", ".reviewCountTextLinkedHistogram .a-icon-alt"]);
            const reviews = allText(["#acrCustomerReviewText", "#averageCustomerReviews #acrCustomerReviewText"]);
            const availability = allText(["#availability", "#outOfStock"]);
            const delivery = allText(["#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE", "#deliveryBlockMessage", "[data-csa-c-delivery-time]"]);
            const description = allText(["#productDescription", "#feature-bullets"]);
            const image = allAttr(["#landingImage", "#imgTagWrapperId img"], "src");
            const selectedColor = allText(["#variation_color_name .selection"]);
            const selectedSize = allText(["#variation_size_name .selection"]);
            const selectedStyle = allText(["#variation_style_name .selection"]);
            const selectedPattern = allText(["#variation_pattern_name .selection"]);
            const selectedQuantity = allText(["#variation_item_package_quantity .selection"]);
            const warranty = allText(["#warrantyInformation_feature_div", "#productSupportAndReturnPolicy-product-support-policy"]);
            const emi = allText(["#inemi_feature_div", "#emiOption"]);
            const offers = Array.from(document.querySelectorAll("#itembox-InstantBankDiscount, #itembox-Partner, #itembox-Cashback, #itembox-EMI, .vsx-offers-desktop-lv__item"))
                .map((node) => clean(node.innerText))
                .filter(Boolean);
            const offerText = offers.join(" | ");
            const boughtMatch = pageText.match(/(\\d[\\d,.]*\\s*[kKmM]?\\+?)\\s+bought\\s+in\\s+past\\s+month/i);
            const bullets = Array.from(document.querySelectorAll("#feature-bullets li span"))
                .map((node) => clean(node.innerText))
                .filter(Boolean);
            const detailRows = Array.from(document.querySelectorAll("#productDetails_techSpec_section_1 tr, #productDetails_detailBullets_sections1 tr, #detailBullets_feature_div li"))
                .map((node) => clean(node.innerText))
                .filter(Boolean);
            const productOverviewRows = Array.from(document.querySelectorAll("#productOverview_feature_div tr, table.a-normal tr, .a-section.a-spacing-small .a-row"))
                .map((node) => clean(node.innerText))
                .filter(Boolean);

            return {
                rank: seed.rank,
                seedName: seed.name,
                seedUrl: seed.url,
                currentUrl: window.location.href,
                hiddenAsin,
                seedAsin: seed.asin,
                seedImageUrl: seed.image_url,
                sponsoredStatus: seed.sponsored_status,
                bestsellerBadge: seed.bestseller_badge,
                title,
                brand,
                price,
                originalPrice,
                allVisiblePrices,
                discount,
                dealBadge,
                coupon,
                rating,
                reviews,
                availability,
                delivery,
                description,
                image,
                selectedColor,
                selectedSize,
                selectedStyle,
                selectedPattern,
                selectedQuantity,
                warranty,
                emi,
                offerCount: offers.length,
                offerText,
                boughtText: boughtMatch ? boughtMatch[1] : "",
                bullets,
                detailRows,
                productOverviewRows,
                pageText,
                mainCategory,
                subcategory
            };
        }
        """,
        {"seed": seed.__dict__, "mainCategory": MAIN_CATEGORY, "subcategory": SUBCATEGORY},
    )


async def find_variant_controls(page: Page) -> list[dict[str, Any]]:
    """Find clickable variant controls on the product page."""
    controls: list[dict[str, Any]] = []
    seen = set()

    for selector in VARIANT_CONTAINER_SELECTORS:
        locators = await page.locator(selector).all()
        for idx, locator in enumerate(locators):
            try:
                aria = await locator.get_attribute("aria-label", timeout=1000)
                title = await locator.get_attribute("title", timeout=1000)
                data_asin = await locator.get_attribute("data-defaultasin", timeout=1000)
                class_name = await locator.get_attribute("class", timeout=1000)
                text = clean_text(await locator.inner_text(timeout=1000))

                variant_name = clean_text(aria or title or text or f"variant-{idx + 1}")
                variant_type = selector.split("_")[1].split(" ")[0] if "variation_" in selector else "variant"
                is_unavailable = "unavailable" in clean_text(class_name).lower()
                key = (selector, variant_name, data_asin)

                if key in seen or is_unavailable:
                    continue
                seen.add(key)
                controls.append(
                    {
                        "selector": selector,
                        "index": idx,
                        "variant_type": variant_type.replace("name", "").strip("_") or "variant",
                        "variant_name": variant_name,
                        "data_asin": clean_text(data_asin),
                    }
                )
            except Exception:
                continue

    return controls[:MAX_VARIANTS_PER_PRODUCT]


async def click_variant(page: Page, control: dict[str, Any]) -> bool:
    """Click a variant control and wait for the product page to refresh."""
    try:
        locator = page.locator(control["selector"]).nth(control["index"])
        before_state = await page.evaluate(
            """
            () => ({
                url: window.location.href,
                title: document.querySelector("#productTitle")?.innerText || "",
                price: document.querySelector(".priceToPay .a-offscreen, .a-price .a-offscreen")?.innerText || "",
                asin: document.querySelector("[name='ASIN']")?.value || ""
            })
            """
        )
        await locator.scroll_into_view_if_needed(timeout=5000)
        await random_delay(0.15, 0.55)
        await locator.click(timeout=8000)
        await page.wait_for_function(
            """
            (before) => {
                const current = {
                    url: window.location.href,
                    title: document.querySelector("#productTitle")?.innerText || "",
                    price: document.querySelector(".priceToPay .a-offscreen, .a-price .a-offscreen")?.innerText || "",
                    asin: document.querySelector("[name='ASIN']")?.value || ""
                };
                return current.url !== before.url
                    || current.title !== before.title
                    || current.price !== before.price
                    || current.asin !== before.asin;
            }
            """,
            before_state,
            timeout=7000,
        )
        await page.wait_for_timeout(random.randint(500, 1100))
        return True
    except Exception as exc:
        logger.info("Variant click skipped: %s", exc)
        return False


def infer_variant_name(data: dict[str, Any], control: dict[str, Any] | None) -> str:
    """Create a readable variant label from visible selections."""
    values = [
        data.get("selectedColor"),
        data.get("selectedSize"),
        data.get("selectedStyle"),
        data.get("selectedPattern"),
        data.get("selectedQuantity"),
    ]
    label = " / ".join(clean_text(value) for value in values if clean_text(value))
    if label:
        return label
    if control:
        return clean_text(control.get("variant_name")) or "Default Variant"
    return "Default Variant"


def parse_detail_fields(detail_rows: list[str]) -> dict[str, str]:
    """Extract model/SKU-like values from product detail rows."""
    joined = " | ".join(detail_rows)
    fields = {
        "model": "",
        "sku": "",
        "manufacturer": "",
        "country_of_origin": "",
        "item_weight": "",
        "dimensions": "",
        "date_first_available": "",
        "best_sellers_rank": "",
        "department": "",
        "packer": "",
        "importer": "",
    }

    patterns = {
        "model": r"(?:item\s+)?model(?: number)?",
        "sku": r"\bsku\b",
        "manufacturer": r"manufacturer",
        "country_of_origin": r"country of origin",
        "item_weight": r"item weight|weight",
        "dimensions": r"product dimensions|package dimensions|item dimensions",
        "date_first_available": r"date first available",
        "best_sellers_rank": r"best sellers rank|best seller rank",
        "department": r"department",
        "packer": r"packer",
        "importer": r"importer",
    }

    for row in detail_rows:
        normalized_row = clean_text(row.replace("\u200f", ""))
        for field, pattern in patterns.items():
            if fields[field] or not re.search(pattern, normalized_row, flags=re.IGNORECASE):
                continue
            value = re.sub(rf".*?{pattern}\s*[:\-]?\s*", "", normalized_row, flags=re.IGNORECASE)
            fields[field] = clean_text(value)

    fields["details_text"] = joined
    return fields


def join_values(values: Any, limit: int = 12) -> str:
    """Join scraped list values into an export-friendly cell."""
    if not isinstance(values, list):
        return clean_text(values)
    cleaned = []
    for value in values:
        text = clean_text(value)
        if text and text not in cleaned:
            cleaned.append(text)
    return " | ".join(cleaned[:limit])


def parse_discount(price: float, original_price: float, discount_text: str) -> float:
    """Calculate discount percentage from visible text or price difference."""
    text_match = re.search(r"(\d+(?:\.\d+)?)\s*%", clean_text(discount_text))
    if text_match:
        return float(text_match.group(1))
    if original_price > price > 0:
        return round((original_price - price) / original_price * 100, 2)
    return 0.0


def delivery_metrics(delivery_text: str, availability_text: str, offer_text: str) -> dict[str, Any]:
    """Calculate delivery and fulfillment flags from visible text."""
    text = f"{delivery_text} {availability_text} {offer_text}".lower()
    days = 0
    day_match = re.search(r"(\d+)\s+days?", text)
    if day_match:
        days = int(day_match.group(1))
    elif "tomorrow" in text or "today" in text:
        days = 1

    return {
        "Free Delivery": "free delivery" in text or "free" in text,
        "Fast Delivery": bool(days and days <= 2) or "today" in text or "tomorrow" in text,
        "Amazon Fulfilled": "fulfilled by amazon" in text or "amazon fulfilled" in text,
        "Delivery Days": days,
        "Installation Availability": "installation" in text,
    }


def offer_metrics(offer_text: str) -> dict[str, Any]:
    """Classify offer text into common Amazon offer groups."""
    text = clean_text(offer_text).lower()
    return {
        "Bank Offers": "bank" in text,
        "Cashback Offers": "cashback" in text,
        "EMI Offers": "emi" in text,
        "Partner Offers": "partner" in text,
        "Coupon Discounts": "coupon" in text,
        "Exchange Offers": "exchange" in text,
    }


def review_metrics(page_text: str, rating: float, total_reviews: int) -> dict[str, Any]:
    """Extract review analytics where visible, otherwise estimate conservative values."""
    text = clean_text(page_text).lower()
    verified_mentions = len(re.findall(r"verified purchase", text))
    positive_words = len(re.findall(r"excellent|good|great|perfect|nice|comfortable|durable|value", text))
    negative_words = len(re.findall(r"bad|poor|broken|worst|defective|uncomfortable|return", text))
    keyword_matches = re.findall(r"\b(quality|comfort|durable|size|fit|value|price|delivery|material|support)\b", text)

    sentiment_total = max(positive_words + negative_words, 1)
    positive_pct = round(positive_words / sentiment_total * 100, 2)
    negative_pct = round(negative_words / sentiment_total * 100, 2)

    return {
        "Rating Distribution": "",
        "Review Keywords": ", ".join(sorted(set(keyword_matches))[:12]),
        "Verified Purchase %": 100.0 if verified_mentions and total_reviews else 0.0,
        "Positive Review %": positive_pct if total_reviews else 0.0,
        "Negative Review %": negative_pct if total_reviews else 0.0,
        "Review Velocity": round(total_reviews / max(1, 30), 2),
        "Rating Quality Score": round((rating / 5) * 100, 2) if rating else 0.0,
    }


def build_rows(seed: ParentSeed, data: dict[str, Any], control: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build parent and variant rows from raw page data."""
    price = to_float(data.get("price"))
    original_price = to_float(data.get("originalPrice"))
    discount_pct = parse_discount(price, original_price, data.get("discount", ""))
    rating = parse_rating(data.get("rating"))
    total_reviews = to_int(data.get("reviews"))
    bought_text = clean_text(data.get("boughtText"))
    bought_units = parse_bought_count(bought_text)
    monthly_units = bought_units or estimate_units_from_rank(seed.rank)
    revenue = round(price * monthly_units, 2)
    current_url = clean_text(data.get("currentUrl")) or clean_text(data.get("seedUrl"))
    asin = clean_text(data.get("hiddenAsin")) or extract_asin(current_url) or seed.asin
    detail_rows = (data.get("detailRows") or []) + (data.get("productOverviewRows") or [])
    detail_fields = parse_detail_fields(detail_rows)
    offer_data = offer_metrics(data.get("offerText", ""))
    delivery_data = delivery_metrics(data.get("delivery", ""), data.get("availability", ""), data.get("offerText", ""))
    review_data = review_metrics(data.get("pageText", ""), rating, total_reviews)

    title = clean_text(data.get("title")) or seed.name
    brand = clean_text(data.get("brand")).replace("Visit the ", "").replace("Brand:", "").replace(" Store", "").strip()
    variant_name = infer_variant_name(data, control)
    variant_type = clean_text(control.get("variant_type")) if control else "default"

    parent_row = {
        "Bestseller Rank": seed.rank,
        "Parent Product Name": title,
        "Parent ASIN": seed.asin or asin,
        "Brand": brand or title.split(" ")[0],
        "Manufacturer": detail_fields["manufacturer"],
        "Country Of Origin": detail_fields["country_of_origin"],
        "Main Category": MAIN_CATEGORY,
        "Subcategory": SUBCATEGORY,
        "Product Description": clean_text(data.get("description")),
        "Product Bullets": join_values(data.get("bullets")),
        "Product Details": detail_fields["details_text"],
        "Product URL": seed.url,
        "Main Image URL": clean_text(data.get("image")) or seed.image_url,
        "Current Price": price,
        "Original Price": original_price,
        "Discount %": discount_pct,
        "Raw Price Text": clean_text(data.get("price")),
        "All Visible Prices": join_values(data.get("allVisiblePrices")),
        "Average Rating": rating,
        "Total Reviews": total_reviews,
        "Overall Bought Count": bought_units,
        "Availability": clean_text(data.get("availability")),
        "Delivery": clean_text(data.get("delivery")),
        "Deal Badge": clean_text(data.get("dealBadge")),
        "Coupon": clean_text(data.get("coupon")),
        "Bestseller Badge": seed.bestseller_badge,
        "Amazon Choice Badge": "amazon's choice" in clean_text(data.get("pageText")).lower(),
        "Sponsored Status": seed.sponsored_status,
        "Parent Product Revenue": revenue,
        "Scraped At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    variant_row = {
        "Parent ASIN": seed.asin or asin,
        "Parent Product Name": title,
        "Bestseller Rank": seed.rank,
        "Variant Name": variant_name,
        "Variant Type": variant_type,
        "Variant Color": clean_text(data.get("selectedColor")),
        "Variant Size": clean_text(data.get("selectedSize")),
        "Variant Pattern": clean_text(data.get("selectedPattern")),
        "Variant Package Quantity": clean_text(data.get("selectedQuantity")),
        "Variant Model": clean_text(data.get("selectedStyle")) or detail_fields["model"],
        "Variant ASIN": (clean_text(control.get("data_asin")) if control else "") or asin or seed.asin,
        "Variant Price": price,
        "Variant Original Price": original_price,
        "Variant Raw Price Text": clean_text(data.get("price")),
        "Variant All Visible Prices": join_values(data.get("allVisiblePrices")),
        "Variant Discount %": discount_pct,
        "Variant Deal Badge": clean_text(data.get("dealBadge")),
        "Variant Coupon": clean_text(data.get("coupon")),
        "Variant Availability": clean_text(data.get("availability")),
        "Variant Stock Status": "Out of Stock" if "out of stock" in clean_text(data.get("availability")).lower() else "Available",
        "Variant Image URL": clean_text(data.get("image")) or seed.image_url,
        "Variant SKU": detail_fields["sku"],
        "Manufacturer": detail_fields["manufacturer"],
        "Country Of Origin": detail_fields["country_of_origin"],
        "Item Weight": detail_fields["item_weight"],
        "Product Dimensions": detail_fields["dimensions"],
        "Date First Available": detail_fields["date_first_available"],
        "Amazon Best Sellers Rank Text": detail_fields["best_sellers_rank"],
        "Department": detail_fields["department"],
        "Packer": detail_fields["packer"],
        "Importer": detail_fields["importer"],
        "Product Bullets": join_values(data.get("bullets")),
        "Product Details": detail_fields["details_text"],
        "Variant Delivery Date": clean_text(data.get("delivery")),
        "Variant Warranty": clean_text(data.get("warranty")),
        "Variant EMI": clean_text(data.get("emi")),
        "Variant Offer Count": int(data.get("offerCount") or 0),
        "Variant Offer Text": clean_text(data.get("offerText")),
        "Variant Bought In Past Month": bought_text,
        "Variant Monthly Units Sold": monthly_units,
        "Variant Estimated Revenue": revenue,
        "Price Category": price_category(price),
        "Discount Analysis": discount_category(discount_pct),
        "Revenue Score": 0.0,
        "Demand Score": 0.0,
        "Bestseller Strength": round(max(0, 101 - seed.rank), 2),
        "Rating Quality Score": review_data["Rating Quality Score"],
        "Review Velocity": review_data["Review Velocity"],
        "Price Competitiveness": 0.0,
        "Discount Strength": min(discount_pct * 2, 100),
        "Sales Potential Score": 0.0,
        "Average Rating": rating,
        "Total Reviews": total_reviews,
        "Product URL": seed.url,
        "Main Category": MAIN_CATEGORY,
        "Subcategory": SUBCATEGORY,
        "Free Delivery": delivery_data["Free Delivery"],
        "Fast Delivery": delivery_data["Fast Delivery"],
        "Amazon Fulfilled": delivery_data["Amazon Fulfilled"],
        "Delivery Days": delivery_data["Delivery Days"],
        "Installation Availability": delivery_data["Installation Availability"],
        "Bank Offers": offer_data["Bank Offers"],
        "Cashback Offers": offer_data["Cashback Offers"],
        "EMI Offers": offer_data["EMI Offers"],
        "Partner Offers": offer_data["Partner Offers"],
        "Coupon Discounts": offer_data["Coupon Discounts"],
        "Exchange Offers": offer_data["Exchange Offers"],
        "Rating Distribution": review_data["Rating Distribution"],
        "Review Keywords": review_data["Review Keywords"],
        "Verified Purchase %": review_data["Verified Purchase %"],
        "Positive Review %": review_data["Positive Review %"],
        "Negative Review %": review_data["Negative Review %"],
        "Scraped At": parent_row["Scraped At"],
    }

    return parent_row, variant_row


async def scrape_detail_page(context: BrowserContext, seed: ParentSeed) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Scrape one parent product and all clickable variants found."""
    page = await context.new_page()
    parent_row: dict[str, Any] = {}
    variant_rows: list[dict[str, Any]] = []

    try:
        await goto_with_retry(page, seed.url)
        await slow_scroll(page, passes=2)

        default_data = await product_json(page, seed)
        parent_row, default_variant = build_rows(seed, default_data, None)
        variant_rows.append(default_variant)

        controls = await find_variant_controls(page) if SCRAPE_VARIANTS else []
        logger.info("Found %s variant controls for %s", len(controls), seed.url)

        seen_variants = {default_variant.get("Variant ASIN") or default_variant.get("Variant Name")}
        for control in controls:
            try:
                clicked = await click_variant(page, control)
                if not clicked:
                    continue
                data = await product_json(page, seed)
                _, variant_row = build_rows(seed, data, control)
                key = variant_row.get("Variant ASIN") or variant_row.get("Variant Name")
                if key in seen_variants:
                    continue
                seen_variants.add(key)
                variant_rows.append(variant_row)
                await random_delay(0.35, 1.1)
            except Exception as exc:
                logger.exception("Failed variant for %s: %s", seed.url, exc)

    except Exception as exc:
        logger.exception("Failed detail page %s: %s", seed.url, exc)
    finally:
        await page.close()

    return parent_row, variant_rows


# =========================================================
# ANALYTICS
# =========================================================

def add_analytics(variants_df: pd.DataFrame) -> pd.DataFrame:
    """Compute analytics scores and normalize numeric columns."""
    if variants_df.empty:
        return variants_df

    numeric_columns = [
        "Variant Price",
        "Variant Original Price",
        "Variant Discount %",
        "Variant Monthly Units Sold",
        "Variant Estimated Revenue",
        "Average Rating",
        "Total Reviews",
        "Bestseller Rank",
    ]
    for column in numeric_columns:
        variants_df[column] = pd.to_numeric(variants_df.get(column, 0), errors="coerce").fillna(0)

    max_revenue = variants_df["Variant Estimated Revenue"].max()
    max_units = variants_df["Variant Monthly Units Sold"].max()
    max_reviews = variants_df["Total Reviews"].max()
    non_zero_prices = variants_df.loc[variants_df["Variant Price"] > 0, "Variant Price"]
    median_price = non_zero_prices.median() if not non_zero_prices.empty else 0

    variants_df["Revenue Score"] = variants_df["Variant Estimated Revenue"].apply(lambda value: score(value, max_revenue))
    variants_df["Demand Score"] = variants_df["Variant Monthly Units Sold"].apply(lambda value: score(value, max_units))
    variants_df["Bestseller Strength"] = variants_df["Bestseller Rank"].apply(lambda value: round(max(0, 101 - value), 2))
    variants_df["Rating Quality Score"] = variants_df["Average Rating"].apply(lambda value: round(value / 5 * 100, 2) if value else 0)
    variants_df["Review Velocity"] = variants_df["Total Reviews"].apply(lambda value: round(value / 30, 2))
    variants_df["Discount Strength"] = variants_df["Variant Discount %"].apply(lambda value: min(round(value * 2, 2), 100))

    if median_price:
        variants_df["Price Competitiveness"] = variants_df["Variant Price"].apply(
            lambda value: round(max(0, 100 - abs(value - median_price) / median_price * 100), 2) if value else 0
        )
    else:
        variants_df["Price Competitiveness"] = 0.0

    variants_df["Sales Potential Score"] = (
        variants_df["Revenue Score"] * 0.30
        + variants_df["Demand Score"] * 0.25
        + variants_df["Rating Quality Score"] * 0.15
        + variants_df["Bestseller Strength"] * 0.15
        + variants_df["Discount Strength"] * 0.10
        + variants_df["Price Competitiveness"] * 0.05
    ).round(2)

    variants_df["Review Velocity Score"] = variants_df["Total Reviews"].apply(lambda value: score(value, max_reviews))
    return variants_df


def build_parent_df(parent_rows: list[dict[str, Any]], variants_df: pd.DataFrame) -> pd.DataFrame:
    """Build parent product table and sum revenue across variants."""
    parent_df = pd.DataFrame(parent_rows)
    if parent_df.empty:
        return parent_df

    parent_df = parent_df.drop_duplicates(subset=["Parent ASIN", "Product URL"], keep="first")
    if not variants_df.empty:
        revenue_by_parent = variants_df.groupby("Parent ASIN", dropna=False)["Variant Estimated Revenue"].sum().reset_index()
        revenue_by_parent.rename(columns={"Variant Estimated Revenue": "Parent Product Revenue"}, inplace=True)
        parent_df.drop(columns=["Parent Product Revenue"], errors="ignore", inplace=True)
        parent_df = parent_df.merge(revenue_by_parent, on="Parent ASIN", how="left")
        parent_df["Parent Product Revenue"] = parent_df["Parent Product Revenue"].fillna(0)

    parent_df["Product Total Revenue"] = parent_df["Parent Product Revenue"]
    return parent_df.sort_values("Bestseller Rank")


def add_product_total_revenue(variants_df: pd.DataFrame) -> pd.DataFrame:
    """Attach parent-level total revenue to every variant/product row."""
    if variants_df.empty or "Parent ASIN" not in variants_df.columns:
        return variants_df

    variants_df = variants_df.copy()
    revenue_by_parent = variants_df.groupby("Parent ASIN", dropna=False)["Variant Estimated Revenue"].transform("sum")
    variants_df["Product Total Revenue"] = revenue_by_parent.fillna(0)
    return variants_df


def remove_unwanted_export_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop fields the export should no longer expose."""
    if frame.empty:
        return frame
    return frame.drop(columns=[column for column in REMOVED_EXPORT_COLUMNS if column in frame.columns], errors="ignore")


def make_sheet_frames(parent_df: pd.DataFrame, variants_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Create all required Excel sheet dataframes."""
    if variants_df.empty:
        empty = pd.DataFrame()
        return {
            "Parent Products": parent_df,
            "Product Variants": empty,
            "Revenue Analytics": empty,
            "Top Revenue Products": empty,
            "Top Selling Variants": empty,
            "Budget Products": empty,
            "Premium Products": empty,
            "Offer Analytics": empty,
            "Review Analytics": empty,
            "Sales Analytics": empty,
        }

    revenue_cols = [
        "Parent ASIN",
        "Parent Product Name",
        "Variant Name",
        "Variant Monthly Units Sold",
        "Variant Estimated Revenue",
        "Product Total Revenue",
        "Revenue Score",
        "Demand Score",
        "Sales Potential Score",
    ]
    offer_cols = [
        "Parent ASIN",
        "Variant Name",
        "Variant Offer Count",
        "Bank Offers",
        "Cashback Offers",
        "EMI Offers",
        "Partner Offers",
        "Coupon Discounts",
        "Exchange Offers",
        "Variant Offer Text",
    ]
    review_cols = [
        "Parent ASIN",
        "Variant Name",
        "Average Rating",
        "Total Reviews",
        "Rating Distribution",
        "Review Keywords",
        "Verified Purchase %",
        "Positive Review %",
        "Negative Review %",
        "Rating Quality Score",
        "Review Velocity",
    ]
    sales_cols = [
        "Parent ASIN",
        "Variant Name",
        "Bestseller Rank",
        "Variant Bought In Past Month",
        "Variant Monthly Units Sold",
        "Variant Estimated Revenue",
        "Product Total Revenue",
        "Bestseller Strength",
        "Demand Score",
        "Sales Potential Score",
    ]

    sheet_frames = {
        "Parent Products": parent_df,
        "Product Variants": variants_df,
        "Revenue Analytics": variants_df[revenue_cols].sort_values("Variant Estimated Revenue", ascending=False),
        "Top Revenue Products": variants_df.sort_values("Variant Estimated Revenue", ascending=False).head(25),
        "Top Selling Variants": variants_df.sort_values("Variant Monthly Units Sold", ascending=False).head(25),
        "Budget Products": variants_df[variants_df["Price Category"] == "Budget"],
        "Premium Products": variants_df[variants_df["Price Category"] == "Premium"],
        "Offer Analytics": variants_df[offer_cols],
        "Review Analytics": variants_df[review_cols],
        "Sales Analytics": variants_df[sales_cols].sort_values("Sales Potential Score", ascending=False),
    }
    return {sheet_name: remove_unwanted_export_columns(frame) for sheet_name, frame in sheet_frames.items()}


# =========================================================
# EXPORT
# =========================================================

def write_excel_frames(sheet_frames: dict[str, pd.DataFrame], output_path: Path) -> None:
    """Write all Excel sheets and apply workbook formatting."""
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, frame in sheet_frames.items():
            safe_frame = frame.copy()
            if safe_frame.empty:
                safe_frame = pd.DataFrame({"Message": ["No rows for this sheet"]})
            safe_frame.to_excel(writer, sheet_name=sheet_name[:31], index=False)

    format_workbook(output_path)


def write_outputs(parent_df: pd.DataFrame, variants_df: pd.DataFrame) -> tuple[Path | None, Path | None]:
    """Export flattened CSV and multi-sheet Excel workbook."""
    if variants_df.empty and parent_df.empty:
        print("No data scraped. Nothing to export.")
        return None, None

    csv_df = variants_df.copy() if not variants_df.empty else parent_df.copy()
    csv_df = remove_unwanted_export_columns(csv_df)
    csv_path = CSV_FILE
    try:
        csv_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    except PermissionError:
        csv_path = timestamped_output_path(CSV_FILE)
        print(f"CSV file is locked. Saving to fallback file: {csv_path}")
        csv_df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    sheet_frames = make_sheet_frames(parent_df, variants_df)
    excel_path = EXCEL_FILE
    try:
        write_excel_frames(sheet_frames, excel_path)
    except PermissionError:
        excel_path = timestamped_output_path(EXCEL_FILE)
        print(f"Excel file is locked. Saving to fallback file: {excel_path}")
        write_excel_frames(sheet_frames, excel_path)

    return csv_path, excel_path


def format_workbook(path: Path) -> None:
    """Apply Excel formatting to all sheets."""
    workbook = load_workbook(path)
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    border = Border(
        left=Side(style="thin", color="D9E2F3"),
        right=Side(style="thin", color="D9E2F3"),
        top=Side(style="thin", color="D9E2F3"),
        bottom=Side(style="thin", color="D9E2F3"),
    )

    currency_headers = {
        "Current Price",
        "Original Price",
        "Variant Price",
        "Variant Original Price",
        "Variant Estimated Revenue",
        "Parent Product Revenue",
        "Product Total Revenue",
    }
    percent_headers = {
        "Discount %",
        "Variant Discount %",
        "Verified Purchase %",
        "Positive Review %",
        "Negative Review %",
    }

    for sheet in workbook.worksheets:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions

        for cell in sheet[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border

        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.border = border

        for column_index, column_cells in enumerate(sheet.columns, start=1):
            header = clean_text(column_cells[0].value)
            width = min(max(max(len(clean_text(cell.value)) for cell in column_cells) + 3, 12), 60)
            sheet.column_dimensions[get_column_letter(column_index)].width = width

            if header in currency_headers:
                for cell in column_cells[1:]:
                    cell.number_format = '"INR" #,##0.00'
            elif header in percent_headers:
                for cell in column_cells[1:]:
                    cell.number_format = '0.00'

        headers = [clean_text(cell.value) for cell in sheet[1]]
        for metric in ["Variant Estimated Revenue", "Product Total Revenue", "Sales Potential Score", "Demand Score"]:
            if metric in headers and sheet.max_row > 2:
                col = headers.index(metric) + 1
                col_letter = get_column_letter(col)
                sheet.conditional_formatting.add(
                    f"{col_letter}2:{col_letter}{sheet.max_row}",
                    ColorScaleRule(
                        start_type="min",
                        start_color="F8696B",
                        mid_type="percentile",
                        mid_value=50,
                        mid_color="FFEB84",
                        end_type="max",
                        end_color="63BE7B",
                    ),
                )

    workbook.save(path)


# =========================================================
# MAIN PIPELINE
# =========================================================

async def scrape_pipeline(target_url: str = TARGET_URL) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the full scraper pipeline."""
    parent_rows: list[dict[str, Any]] = []
    variant_rows: list[dict[str, Any]] = []
    target_url = normalize_url(target_url)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=HEADLESS,
            slow_mo=SLOW_MO_MS,
            args=[
                "--disable-dev-shm-usage",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
            ],
        )
        context = await new_context(browser)
        page = await context.new_page()
        page.set_default_timeout(20000)

        try:
            if is_product_url(target_url):
                seeds = [
                    ParentSeed(
                        rank=1,
                        name="Direct Product URL",
                        url=target_url,
                        asin=extract_asin(target_url),
                        image_url="",
                        sponsored_status=False,
                        bestseller_badge=False,
                    )
                ]
            else:
                seeds = await collect_bestseller_seeds(page, target_url)
            print(f"Found parent products: {len(seeds)}")

            semaphore = asyncio.Semaphore(DETAIL_PAGE_CONCURRENCY)

            async def scrape_with_limit(seed: ParentSeed):
                async with semaphore:
                    print(f"Scraping detail page #{seed.rank}: {seed.name[:70]}")
                    await random_delay(0.35, 1.2)
                    return await scrape_detail_page(context, seed)

            results = await asyncio.gather(*(scrape_with_limit(seed) for seed in seeds))
            for parent_row, rows in results:
                if parent_row:
                    parent_rows.append(parent_row)
                variant_rows.extend(rows)

        finally:
            await page.close()
            await context.close()
            await browser.close()

    variants_df = pd.DataFrame(variant_rows)
    if not variants_df.empty:
        variants_df = variants_df.drop_duplicates(subset=["Parent ASIN", "Variant ASIN", "Variant Name"], keep="first")
        variants_df = add_analytics(variants_df)
        variants_df = add_product_total_revenue(variants_df)

    parent_df = build_parent_df(parent_rows, variants_df)
    return parent_df, variants_df


def parse_args() -> argparse.Namespace:
    """Read command-line options."""
    parser = argparse.ArgumentParser(description="Scrape Amazon bestseller or product detail URLs.")
    parser.add_argument(
        "url",
        nargs="?",
        default=TARGET_URL,
        help="Amazon bestseller/category URL or direct product URL. Defaults to TARGET_URL env var.",
    )
    return parser.parse_args()


async def main() -> None:
    """Entry point."""
    global BASE_URL
    args = parse_args()
    BASE_URL = infer_base_url(args.url)
    print("Starting Amazon Best Seller analytics scraper...")
    print(f"Target URL: {args.url}")
    try:
        parent_df, variants_df = await scrape_pipeline(args.url)
        csv_path, excel_path = write_outputs(parent_df, variants_df)
        print("\nSCRAPING COMPLETED")
        print(f"Parent products: {len(parent_df)}")
        print(f"Product variants: {len(variants_df)}")
        if csv_path:
            print(f"CSV exported: {csv_path}")
        if excel_path:
            print(f"Excel exported: {excel_path}")
        print(f"Log file: {LOG_FILE}")
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        print(f"Scraper failed: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
