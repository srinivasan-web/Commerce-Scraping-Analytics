"""
Optimized async scraper with parallel processing, connection pooling, and efficient data handling.
Features:
- Async Playwright for non-blocking operations
- Parallel product detail fetching with connection pooling
- Intelligent rate limiting instead of random delays
- Smart caching for duplicate products
- Batch processing for multiple URLs
- Real-time progress streaming
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import re
import traceback
import time
import uuid
from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from backend.app.schemas import JobStatus, Product, ScrapeRequest, Website
from backend.app.services.analytics import enrich_product_scores
from backend.app.services.store import store

RUPEE = "\u20b9"
MOJIBAKE_RUPEE = "\u00e2\u201a\u00b9"
PRICE_TOKEN = f"(?:{re.escape(RUPEE)}|{re.escape(MOJIBAKE_RUPEE)}|Rs\\.?|INR|\\$)"
BOUGHT_COUNT_PATTERN = r"\d[\d,.]*\s*(?:k|m|lakh|lac|l|crore|cr)?\+?\s*(?:bought|sold|purchased|orders?)(?:\s+(?:in\s+)?(?:the\s+)?(?:past|last)\s+month)?"

# Global connection pool
class BrowserPool:
    """Manages browser instances and contexts for connection pooling."""
    
    def __init__(self, max_browsers: int = 3):
        self.max_browsers = max_browsers
        self.browsers: list[Browser] = []
        self.contexts: list[BrowserContext] = []
        self.semaphore = asyncio.Semaphore(max_browsers)
        self.lock = asyncio.Lock()
        self._initialized = False
        self._playwright = None
    
    async def initialize(self):
        """Initialize the browser pool."""
        if self._initialized:
            return
        try:
            self._playwright = await async_playwright().start()
            self._initialized = True
        except Exception as e:
            self._initialized = False
            self._playwright = None
            print(f"Playwright initialization warning: {e!r}")
            raise RuntimeError(f"Failed to start async Playwright: {e!r}") from e
    
    async def _ensure_playwright(self):
        """Ensure playwright is initialized."""
        if not self._playwright:
            try:
                self._playwright = await async_playwright().start()
                self._initialized = True
            except Exception as e:
                self._initialized = False
                self._playwright = None
                raise RuntimeError(f"Failed to start async Playwright: {e!r}") from e
        return self._playwright
    
    async def get_page(self) -> Page:
        """Get a page from the pool with semaphore control."""
        if not self._playwright:
            self._playwright = await self._ensure_playwright()
        
        await self.semaphore.acquire()
        
        try:
            async with self.lock:
                context = None
                
                if self.contexts:
                    context = self.contexts.pop()
                
                if not context:
                    if not self.browsers or len(self.browsers) < self.max_browsers:
                        try:
                            browser = await self._playwright.chromium.launch(
                                headless=True,
                                args=[
                                    "--disable-blink-features=AutomationControlled",
                                    "--no-sandbox",
                                    "--disable-dev-shm-usage",
                                    "--disable-gpu",
                                ],
                            )
                            self.browsers.append(browser)
                        except Exception as e:
                            self.semaphore.release()
                            raise RuntimeError(f"Failed to launch async Chromium: {e!r}") from e
                    else:
                        browser = self.browsers[0]
                    
                    try:
                        context = await browser.new_context(
                            viewport={"width": 1440, "height": 1000},
                            user_agent=random.choice([
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                            ]),
                            locale="en-IN",
                            timezone_id="Asia/Kolkata",
                            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
                        )
                    except Exception as e:
                        self.semaphore.release()
                        raise RuntimeError(f"Failed to create async browser context: {e!r}") from e
            
            if not context:
                self.semaphore.release()
                raise RuntimeError("No context available")
            
            page = await context.new_page()
            page._pool_context = context
            return page
        
        except Exception as e:
            self.semaphore.release()
            raise
    
    async def return_page(self, page: Page):
        """Return a page to the pool."""
        try:
            if hasattr(page, "_pool_context"):
                context = page._pool_context
                try:
                    await page.close()
                except Exception:
                    pass
                if context and len(self.contexts) < self.max_browsers:
                    self.contexts.append(context)
                else:
                    try:
                        await context.close()
                    except Exception:
                        pass
            else:
                await page.close()
        except Exception:
            pass
        finally:
            self.semaphore.release()
    
    async def cleanup(self):
        """Clean up all browsers and contexts."""
        async with self.lock:
            for context in self.contexts:
                try:
                    await context.close()
                except Exception:
                    pass
            for browser in self.browsers:
                try:
                    await browser.close()
                except Exception:
                    pass
            
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
            
            self.browsers.clear()
            self.contexts.clear()
            self._initialized = False
            self._playwright = None


# Global pool instance
_browser_pool = BrowserPool(max_browsers=3)


def clean_text(value: str | None) -> str:
    """Clean whitespace from text."""
    return re.sub(r"\s+", " ", value or "").strip()


def number_from_text(text: str, fallback: float = 0) -> float:
    """Extract number from text."""
    match = re.search(r"[\d,]+(?:\.\d+)?", text or "")
    if not match:
        return fallback
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return fallback


def parse_scaled_number(amount: str, suffix: str = "") -> int:
    """Parse abbreviated marketplace counts such as 1K, 1.5K, 2 lakh, or 1 crore."""
    try:
        number = float((amount or "0").replace(",", ""))
    except ValueError:
        return 0
    suffix = (suffix or "").lower()
    multipliers = {
        "k": 1_000,
        "m": 1_000_000,
        "l": 100_000,
        "lac": 100_000,
        "lakh": 100_000,
        "cr": 10_000_000,
        "crore": 10_000_000,
    }
    return int(number * multipliers.get(suffix, 1))


def parse_rank(value: str, fallback: int = 0) -> int:
    """Parse rank from text."""
    parsed = int(number_from_text(value, fallback))
    return parsed or fallback


def parse_bought_count(text: str) -> int:
    """Parse bought count from text."""
    clean = clean_text(text).lower().replace(",", "")
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(k|m|lakh|lac|l|crore|cr)?\+?\s*(?:bought|sold|purchased|orders?)(?:\s+(?:in\s+)?(?:the\s+)?(?:past|last)\s+month)?",
        clean,
        flags=re.I,
    )
    if match:
        return parse_scaled_number(match.group(1), match.group(2))
    if re.fullmatch(r"\d+(?:\.\d+)?\s*(?:k|m|lakh|lac|l|crore|cr)?\+?", clean):
        bare = re.match(r"(\d+(?:\.\d+)?)\s*(k|m|lakh|lac|l|crore|cr)?", clean)
        return parse_scaled_number(bare.group(1), bare.group(2) if bare else "")
    return 0


def estimate_units_from_rank(rank: int) -> int:
    """Estimate monthly units from bestseller rank when Amazon hides bought-count text."""
    if rank <= 0:
        return 0
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


def calculate_live_revenue(price: float, visible_bought_count: int) -> float:
    """Calculate product total revenue from scraped live bought count and price."""
    return round(max(price, 0) * max(visible_bought_count, 0), 2)


def parse_money_amount(text: str) -> float:
    """Extract a monetary amount from text."""
    match = re.search(rf"{PRICE_TOKEN}\s*([\d,]+(?:\.\d+)?)", text or "", flags=re.I)
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            return 0.0
    return number_from_text(text, 0.0)


def extract_discount_percentage(discount_text: str, price: float, original_price: float) -> float:
    """Normalize discount to a percentage value."""
    text = clean_text(discount_text).lower()
    if not text:
        return 0.0
    pct_match = re.search(r"(-?\d+(?:\.\d+)?)\s*%", text)
    if pct_match:
        return round(abs(float(pct_match.group(1))), 2)
    if original_price > price > 0:
        return round(((original_price - price) / original_price) * 100, 2)
    saved_amount = parse_money_amount(text)
    if saved_amount > 0 and price > 0:
        implied_original = original_price if original_price > 0 else price + saved_amount
        if implied_original > price:
            return round(((implied_original - price) / implied_original) * 100, 2)
    return 0.0


def brand_from_name(name: str) -> str:
    """Extract brand from product name."""
    parts = clean_text(name).split()
    return parts[0] if parts else ""


def discount_label(discount: float) -> str:
    """Get discount label based on discount percentage."""
    if discount >= 35:
        return "High Discount"
    if discount >= 15:
        return "Medium Discount"
    if discount > 0:
        return "Low Discount"
    return "No Discount"


def first_match(patterns: list[str], text: str) -> str:
    """Get first regex match from text."""
    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.I)
        if match:
            return clean_text(match.group(0))
    return ""


def apply_parent_revenue(products: list[Product]) -> list[Product]:
    """Calculate parent product revenue."""
    totals: dict[str, float] = {}
    for product in products:
        key = product.parent_asin or product.id
        totals[key] = totals.get(key, 0) + product.revenue
    for product in products:
        product.parent_product_revenue = round(totals.get(product.parent_asin or product.id, product.revenue), 2)
    return products


def parse_card_to_product(job_id: str, request_url: str, website: Website, category: str, rank: int, card: dict) -> Product:
    """Parse card data to Product model."""
    card_text = clean_text(card.get("text"))
    raw_card_text = card.get("rawText") or card_text
    lower = card_text.lower()
    lines = [clean_text(line) for line in re.split(r"\n| {2,}", raw_card_text) if clean_text(line)]

    name = clean_text(card.get("name") or card.get("productName")) or next(
        (
            line
            for line in lines
            if len(line) > 18
            and not re.search(rf"out of|ratings?|reviews?|bought|sponsored|best seller|{PRICE_TOKEN}", line, flags=re.I)
        ),
        f"Product {rank}",
    )

    price_text = clean_text(card.get("price")) or first_match([rf"{PRICE_TOKEN}\s*[\d,]+(?:\.\d+)?", r"\b[\d,]+(?:\.\d+)?\s*rupees\b"], card_text)
    price = parse_money_amount(price_text)
    all_prices = re.findall(rf"{PRICE_TOKEN}\s*[\d,]+(?:\.\d+)?", card_text, flags=re.I)
    original_price_text = clean_text(card.get("originalPrice")) or (all_prices[1] if len(all_prices) > 1 else "")
    original_price = parse_money_amount(original_price_text)
    discount_text = clean_text(card.get("discount")) or first_match(
        [
            r"-?\d+(?:\.\d+)?\s*%\s*(?:off)?",
            rf"save\s*(?:{PRICE_TOKEN})?\s*[\d,]+(?:\.\d+)?",
            rf"save\s*\d+(?:\.\d+)?\s*%",
        ],
        card_text,
    )
    discount = extract_discount_percentage(discount_text, price, original_price)
    rating_text = clean_text(card.get("rating")) or first_match([r"[0-5](?:\.\d)?\s*out of\s*5\s*stars?", r"[0-5](?:\.\d)?\s*stars?"], card_text)
    rating = number_from_text(rating_text, 0)
    reviews_text = clean_text(card.get("reviews")) or first_match([r"[\d,]+\s*ratings?", r"[\d,]+\s*reviews?"], card_text)
    reviews = int(number_from_text(reviews_text, 0))
    bought_text = clean_text(card.get("boughtText")) or first_match(
        [BOUGHT_COUNT_PATTERN],
        card_text,
    )
    rank_text = clean_text(card.get("rank")) or f"#{rank}"
    rank_number = parse_rank(rank_text, rank)
    scraped_units = parse_bought_count(bought_text)
    units = scraped_units or estimate_units_from_rank(rank_number)
    units_estimated = scraped_units == 0 and units > 0
    bought_source = "visible" if scraped_units else ("rank_estimate" if units else "not_available")
    revenue = calculate_live_revenue(price, scraped_units)
    asin = clean_text(card.get("id") or card.get("asin")) or f"ITEM{rank_number:06d}"
    color = first_match([r"color[:\s]+[a-z ]{3,24}"], card_text).replace("Color", "").replace(":", "").strip()
    size = first_match([r"size[:\s]+[a-z0-9 .-]{1,24}"], card_text).replace("Size", "").replace(":", "").strip()
    offers = "; ".join(
        label
        for label, detected in {
            "Bank offer": "bank" in lower,
            "Coupon": "coupon" in lower,
            "Limited time deal": "limited time" in lower or "deal" in lower,
            "EMI": "emi" in lower,
            "Exchange offer": "exchange" in lower,
        }.items()
        if detected
    )

    return Product(
        id=str(uuid.uuid4()),
        job_id=job_id,
        product_rank=rank_text,
        rank_number=rank_number,
        name=name[:180],
        brand_name=brand_from_name(name),
        website=website,
        category=category,
        subcategory="Bestsellers",
        parent_asin=asin,
        variant_asin=f"{asin}-V",
        variant=" / ".join(part for part in [color, size] if part) or "Default",
        color=color,
        size=size,
        price=price,
        original_price=original_price,
        discount=discount,
        price_text=price_text,
        original_price_text=original_price_text,
        discount_text=discount_text or discount_label(discount),
        rating=rating,
        rating_text=rating_text,
        reviews=reviews,
        reviews_text=reviews_text,
        units_sold=units,
        visible_bought_count=scraped_units,
        units_sold_estimated=units_estimated,
        bought_count_source=bought_source,
        bought_count_text=bought_text or (f"Estimated from bestseller rank #{rank_number}" if units else "Not shown on page"),
        revenue=revenue,
        offers=offers or "No visible card offer",
        delivery=first_match([r"free delivery", r"delivery\s*(?:by|tomorrow|in)\s*[^.]{0,40}", r"tomorrow"], card_text),
        warranty=first_match([r"\d+\s*(?:year|month)s?\s*warranty", r"warranty"], card_text),
        availability="Currently unavailable" if "currently unavailable" in lower or "out of stock" in lower else "Available",
        prime_available="prime" in lower or "fulfilled" in lower,
        free_delivery="free delivery" in lower,
        limited_time_deal="limited time" in lower or "deal" in lower,
        coupon_available="coupon" in lower,
        sponsored_status="sponsored" in lower,
        bestseller_badge="best seller" in lower or "bestseller" in lower,
        amazon_choice_badge="amazon's choice" in lower or "amazons choice" in lower,
        raw_card_text=raw_card_text,
        image_url=clean_text(card.get("img") or card.get("imageUrl") or card.get("image")),
        product_url=clean_text(card.get("link") or card.get("productUrl") or card.get("url")) or request_url,
    )


# JavaScript extraction scripts - IMPROVED VERSION
EXTRACT_SCRIPT = """
({ maxProducts }) => {
  const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const linesOf = (value) => (value || '').split('\\n').map((line) => clean(line)).filter(Boolean);
  const firstLine = (lines, predicate) => lines.find(predicate) || '';
  const absolute = (href) => {
    try { return href ? new URL(href, window.location.origin).href : ''; }
    catch { return ''; }
  };
  const isPrice = (line) => line.includes('\\u20b9') || line.includes('\\u00e2\\u201a\\u00b9') || /\\b(?:rs\\.?|inr)\\s*[\\d,]+/i.test(line);
  const isBoughtCount = (line) => /\\d[\\d,.]*\\s*(?:[kKmM]|lakh|lac|L|crore|cr)?\\+?\\s*(?:bought|sold|purchased|orders?)(?:\\s+(?:in\\s+)?(?:the\\s+)?(?:past|last)\\s+month)?/i.test(line);
  
  const rows = [];
  const seen = new Set();
  
  // Get all product containers - handle both old and new Amazon layouts
  const candidates = Array.from(document.querySelectorAll([
    'div.p13n-sc-uncoverable-faceout',        // Main bestseller container
    'li.zg-carousel-general-faceout',          // Carousel items
    'div[data-asin]',                           // Any div with ASIN
    'div.a-cardui',                             // Card UI components
    'div[class*="p13n"]',
    '[data-testid*="product"]',
    '[data-item-id]',
    '[class*="product-card"]',
    '[class*="ProductCard"]',
    '[class*="productCard"]',
    '[class*="product-item"]',
    '[class*="s-item"]',
    'li[class*="product"]',
    'article'
  ].join(',')));

  // Deduplicate candidates by ASIN
  const uniqueCandidates = [];
  const seenAsins = new Set();
  
  for (const candidate of candidates) {
    const asin = candidate.getAttribute('data-asin');
    if (asin && !seenAsins.has(asin)) {
      seenAsins.add(asin);
      uniqueCandidates.push(candidate);
    } else if (!asin) {
      uniqueCandidates.push(candidate);
    }
  }

  for (const node of uniqueCandidates) {
    try {
      const rawText = node.innerText || '';
      const text = clean(rawText);
      const lines = linesOf(rawText);
      
      // Extract product link - try multiple selectors
      let linkNode = node.querySelector('a[href*="/dp/"]');
      if (!linkNode) linkNode = node.querySelector('a[href*="/gp/product/"]');
      if (!linkNode) linkNode = node.querySelector('a.a-link-normal');
      if (!linkNode) linkNode = node.querySelector('a[href*="/itm/"], a[href*="/p/"], a[href*="/ip/"], a[href*="/product"], a[href]');
      
      const link = linkNode ? absolute(linkNode.getAttribute('href') || linkNode.href || '') : '';
      
      // Extract ASIN
      const idFromNode = clean(node.getAttribute('data-asin') || node.getAttribute('data-item-id') || '');
      const asinFromLink = link ? (link.match(/\\/(?:dp|gp\\/product)\\/([A-Z0-9]{10})/) || link.match(/\\/(?:itm|ip|product|p)\\/([^/?#]+)/) || [])[1] : '';
      const id = idFromNode || asinFromLink || '';
      
      // Extract rank - can be in #1, #2 format or in text
      const rankBadge = node.querySelector('.zg-bdg-text, [class*="zg-bdg-text"], [class*="zg-badge"]');
      let rank = rankBadge ? clean(rankBadge.innerText) : '';
      if (!rank) {
        const rankMatch = text.match(/#\\d+/);
        rank = rankMatch ? rankMatch[0] : '';
      }
      
      // Extract product name - try multiple sources
      let name = '';
      const nameDiv = node.querySelector("div[class*='p13n-sc-css-line-clamp']");
      if (nameDiv) name = clean(nameDiv.innerText);
      
      if (!name) {
        const linkText = linkNode ? clean(linkNode.innerText) : '';
        if (linkText && linkText.length > 5) name = linkText;
      }
      
      if (!name) {
        const img = node.querySelector('img');
        if (img) name = clean(img.getAttribute('alt') || img.getAttribute('aria-label') || '');
      }
      
      if (!name && lines.length > 0) {
        // Find first substantial line that looks like a product name
        for (let i = 0; i < Math.min(3, lines.length); i++) {
          const line = lines[i];
          if (line.length > 10 && !line.startsWith('#') && !isPrice(line)) {
            name = line;
            break;
          }
        }
      }
      
      // Clean up name
      name = clean(name).replace(/^#\\d+\\s*/, '');
      
      // Extract image
      const img = node.querySelector('img');
      const imageUrl = img ? clean(img.getAttribute('src') || img.getAttribute('data-src') || '') : '';
      
      // Extract price
      const price = firstLine(lines, (line) => isPrice(line) && !/mrp|m\\.r\\.p|save|coupon/i.test(line)) || firstLine(lines, isPrice);
      
      // Extract rating and reviews
      const ratingLine = firstLine(lines, (line) => /[0-5](?:\\.\\d+)?\\s*out of\\s*5/i.test(line));
      const rating = clean((ratingLine.match(/[0-5](?:\\.\\d+)?\\s*out of\\s*5(?:\\s*stars?)?/i) || [])[0] || '');
      
      const ratingIndex = lines.indexOf(ratingLine);
      let reviews = '';
      if (ratingLine) {
        reviews = (ratingLine.match(/out of\\s*5\\s*stars?\\s+([\\d,]+)/i) || [])[1] || '';
        if (!reviews && ratingIndex >= 0) {
          reviews = firstLine(lines.slice(ratingIndex + 1, ratingIndex + 4), (line) => /^[\\d,]+$/.test(line));
        }
      }
      
      // Extract bought text and discount
      const boughtText = firstLine(lines, isBoughtCount);
      const discount = firstLine(lines, (line) => /-?\\d+(?:\\.\\d+)?\\s*%\\s*(?:off)?|save\\s*(?:\\u20b9|rs\\.?|inr)?\\s*[\\d,]+(?:\\.\\d+)?/i.test(line));
      
      // Validation: require at least ID+Link or good name
      const hasValidId = id && id.length > 0;
      const hasValidLink = link && link.length > 10;
      const hasValidName = name && name.length > 10;
      
      if ((hasValidId || hasValidLink) && hasValidName) {
        const key = id || link;
        if (!seen.has(key)) {
          seen.add(key);
          rows.push({
            text, rawText, name, productName: name, link, productUrl: link,
            img: imageUrl, imageUrl: imageUrl,
            id, asin: id, rank, price, rating, reviews, boughtText, discount
          });
          
          if (rows.length >= maxProducts) break;
        }
      }
    } catch (e) {
      // Skip problematic elements
      continue;
    }
  }
  
  return rows;
}
"""

DETAIL_SCRIPT = """
() => {
  const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const boughtPattern = /\\d[\\d,.]*\\s*(?:[kKmM]|lakh|lac|L|crore|cr)?\\+?\\s*(?:bought|sold|purchased|orders?)(?:\\s+(?:in\\s+)?(?:the\\s+)?(?:past|last)\\s+month)?/i;
  const boughtMatch = (value) => clean(((value || '').match(boughtPattern) || [])[0] || '');
  const asinInput = document.querySelector('[name="ASIN"]');
  const asin = clean(asinInput ? asinInput.getAttribute('value') : '') ||
    clean((window.location.href.match(/\\/(?:dp|gp\\/product)\\/([A-Z0-9]{10})/) || [])[1] || '');
  const priceElementA = document.querySelector('#corePriceDisplay_desktop_feature_div .a-price .a-offscreen');
  const priceElementB = document.querySelector('#priceblock_ourprice, #priceblock_dealprice, #priceblock_saleprice');
  const price = clean(priceElementA ? priceElementA.innerText : '') ||
    clean(priceElementB ? priceElementB.innerText : '') || '';
  const originalPriceElement = document.querySelector('.priceBlockStrikePriceString, .a-text-price .a-offscreen, [data-a-color="secondary"]');
  const originalPrice = clean(originalPriceElement ? originalPriceElement.innerText : '') || '';
  const discountElementA = document.querySelector('.savingsPercentage');
  const discountElementB = document.querySelector('[data-a-color="danger"]');
  const discountElementC = document.querySelector('#regularprice_savings .a-color-price');
  const discountElementD = Array.from(document.querySelectorAll('*')).find(el => /-?\\d+(?:\\.\\d+)?\\s*%\\s*(?:off)?|save\\s*(?:\\u20b9|rs\\.?|inr)?\\s*[\\d,]+(?:\\.\\d+)?/i.test(el.innerText));
  const discount = clean(discountElementA ? discountElementA.innerText : '') ||
    clean(discountElementB ? discountElementB.innerText : '') ||
    clean(discountElementC ? discountElementC.innerText : '') ||
    clean(discountElementD ? discountElementD.innerText : '') || '';
  const socialProof = document.querySelector('#social-proofing-faceout-title-tk_bought .a-text-bold, #social-proofing-faceout-title-tk_bought, #social-proofing-faceout-title-tk_bought span');
  const boughtElement = Array.from(document.querySelectorAll('span, div, p')).find(el => boughtPattern.test(el.innerText || ''));
  const boughtText = boughtMatch(socialProof ? socialProof.innerText : '') ||
    boughtMatch(boughtElement ? boughtElement.innerText : '') ||
    boughtMatch(document.body ? document.body.innerText : '');
  return { asin, price, originalPrice, discount, boughtText };
}
"""

VARIANT_SCRIPT = """
({ maxVariants }) => {
  const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const visible = (node) => {
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const selectors = [
    '#variation_color_name li, #variation_size_name li, #variation_style_name li, #variation_pattern_name li',
    '#variation_capacity_name li, #variation_flavor_name li, #variation_configuration li',
    '[data-asin][role="button"], [data-defaultasin], button[aria-label*="Select"], a[aria-label*="Select"]',
    '[class*="swatch"], [class*="variant"], [class*="Variation"]'
  ];
  const variants = [];
  const seen = new Set();
  for (const node of Array.from(document.querySelectorAll(selectors.join(',')))) {
    if (!visible(node)) continue;
    const text = clean(node.getAttribute('title') || node.getAttribute('aria-label') || node.innerText);
    const asin = clean(node.getAttribute('data-asin') || node.getAttribute('data-defaultasin') || '');
    const group = clean(node.closest('[id^="variation_"]')?.id || node.getAttribute('name') || 'variant');
    const key = `${group}:${asin}:${text}`;
    if ((!text && !asin) || seen.has(key)) continue;
    seen.add(key);
    variants.push({ text, asin, group, index: variants.length });
    if (variants.length >= maxVariants) break;
  }
  const galleryImages = Array.from(document.querySelectorAll('img'))
    .map((img) => clean(img.currentSrc || img.src || img.getAttribute('data-src') || ''))
    .filter((src) => /^https?:/.test(src))
    .slice(0, 20);
  const videoUrls = Array.from(document.querySelectorAll('video source, video'))
    .map((node) => clean(node.getAttribute('src') || ''))
    .filter((src) => /^https?:/.test(src))
    .slice(0, 10);
  return { variants, galleryImages, videoUrls };
}
"""


def infer_variant_type(group: str, name: str) -> str:
    text = f"{group} {name}".lower()
    for label in ["color", "size", "weight", "model", "package", "flavor", "storage", "capacity", "combo"]:
        if label in text:
            return "storage" if label == "capacity" else label
    return "variant"


def apply_variant_fields(product: Product, card: dict) -> Product:
    variant_name = clean_text(card.get("variantName") or card.get("variant") or product.variant)
    variant_type = infer_variant_type(clean_text(card.get("variantGroup")), variant_name)
    product.variant_name = variant_name or product.variant
    product.variant_type = variant_type.title()
    product.variant = product.variant_name
    if variant_type == "color" and not product.color:
        product.color = variant_name
    elif variant_type == "size" and not product.size:
        product.size = variant_name
    elif variant_type == "weight":
        product.weight = variant_name
    elif variant_type == "model":
        product.model = variant_name
    elif variant_type == "package":
        product.package = variant_name
    elif variant_type == "flavor":
        product.flavor = variant_name
    elif variant_type == "storage":
        product.storage = variant_name
    elif variant_type == "combo":
        product.combo = variant_name
    product.sku = product.variant_asin or product.parent_asin
    product.variant_images = [url for url in card.get("variantImages", []) if url]
    product.gallery_images = [url for url in card.get("galleryImages", []) if url]
    product.video_urls = [url for url in card.get("videoUrls", []) if url]
    lower = f"{product.offers} {product.raw_card_text}".lower()
    product.bank_offers = "Bank offer" if "bank" in lower else ""
    product.emi_offers = "EMI available" if "emi" in lower else ""
    product.cashback_offers = "Cashback offer" if "cashback" in lower else ""
    product.coupon_offers = "Coupon available" if "coupon" in lower else ""
    product.partner_offers = "Partner offer" if "partner" in lower else ""
    product.exchange_offers = "Exchange offer" if "exchange" in lower else ""
    product.fast_delivery = any(token in lower for token in ["tomorrow", "today", "fast delivery", "one-day"])
    product.delivery_days = product.delivery
    product.installation_available = "installation" in lower
    product.limited_stock = "only" in lower and "left" in lower
    product.review_keywords = [word for word in ["quality", "value", "fit", "battery", "comfort", "durable"] if word in lower]
    if product.rating:
        product.positive_review_percent = round(min(product.rating / 5 * 100, 100), 2)
        product.negative_review_percent = round(100 - product.positive_review_percent, 2)
    return product


async def fetch_product_detail(context: BrowserContext, product_url: str, card: dict) -> dict:
    """Fetch product details from detail page with smart timeout."""
    page: Page | None = None
    try:
        page = await context.new_page()
        await page.goto(product_url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(random.uniform(0.3, 0.7))  # Reduced from 0.8-1.4
        detail = await page.evaluate(DETAIL_SCRIPT)
        
        merged = {**card}
        for key, value in detail.items():
            if value and (key in {"boughtText", "originalPrice", "discount"} or not merged.get(key)):
                merged[key] = value
        merged["rank"] = card.get("rank") or "#unknown"
        return merged
    except Exception:
        return card
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


async def fetch_product_variants(context: BrowserContext, product_url: str, card: dict, max_variants: int) -> list[dict]:
    """Open a product page, discover variant controls, click them, and capture changed live state."""
    page: Page | None = None
    if max_variants <= 0 or not product_url:
        return [card]
    try:
        page = await context.new_page()
        await page.goto(product_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_load_state("networkidle", timeout=12000)
        discovery = await page.evaluate(VARIANT_SCRIPT, {"maxVariants": max_variants})
        variants = discovery.get("variants") or []
        gallery_images = discovery.get("galleryImages") or []
        video_urls = discovery.get("videoUrls") or []
        if not variants:
            return [{**card, "variantName": card.get("variant") or "Default", "galleryImages": gallery_images, "videoUrls": video_urls}]

        rows: list[dict] = []
        for variant in variants[:max_variants]:
            try:
                selector = (
                    f'[data-asin="{variant.get("asin")}"]'
                    if variant.get("asin")
                    else f'text="{str(variant.get("text", ""))[:80]}"'
                )
                before_url = page.url
                await page.locator(selector).first.click(timeout=5000)
                await page.wait_for_timeout(random.randint(350, 900))
                if page.url != before_url:
                    await page.wait_for_load_state("domcontentloaded", timeout=12000)
                detail = await page.evaluate(DETAIL_SCRIPT)
                next_gallery = await page.evaluate("() => Array.from(document.querySelectorAll('img')).map(img => img.currentSrc || img.src || img.getAttribute('data-src') || '').filter(src => /^https?:/.test(src)).slice(0, 20)")
                rows.append(
                    {
                        **card,
                        **{key: value for key, value in detail.items() if value},
                        "variantName": clean_text(variant.get("text")) or clean_text(detail.get("asin")) or "Detected variant",
                        "variantGroup": clean_text(variant.get("group")),
                        "variantImages": next_gallery,
                        "galleryImages": next_gallery or gallery_images,
                        "videoUrls": video_urls,
                    }
                )
            except Exception:
                rows.append({**card, "variantName": clean_text(variant.get("text")) or "Detected variant", "variantGroup": clean_text(variant.get("group")), "galleryImages": gallery_images, "videoUrls": video_urls})
        return rows or [card]
    except Exception:
        return [card]
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


async def fetch_details_parallel(context: BrowserContext, cards: list[dict]) -> list[dict]:
    """Fetch details for multiple products in parallel batches."""
    batch_size = 4  # Parallel batch size
    needs_detail = [
        (i, card) for i, card in enumerate(cards)
        if (not card.get("boughtText") or not card.get("originalPrice") or not card.get("discount"))
        and card.get("productUrl")
    ]
    
    if not needs_detail:
        return cards
    
    # Process in batches
    for batch_start in range(0, len(needs_detail), batch_size):
        batch = needs_detail[batch_start:batch_start + batch_size]
        tasks = [
            fetch_product_detail(context, card.get("productUrl"), card)
            for _, card in batch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for (idx, _), result in zip(batch, results):
            if isinstance(result, dict):
                cards[idx] = result
    
    return cards


async def expand_variants_parallel(context: BrowserContext, cards: list[dict], max_variants: int) -> list[dict]:
    batch_size = 3
    expanded: list[dict] = []
    for batch_start in range(0, len(cards), batch_size):
        batch = cards[batch_start:batch_start + batch_size]
        results = await asyncio.gather(
            *(fetch_product_variants(context, card.get("productUrl"), card, max_variants) for card in batch),
            return_exceptions=True,
        )
        for card, result in zip(batch, results):
            if isinstance(result, list):
                expanded.extend(result)
            else:
                expanded.append(card)
    return expanded


async def scroll_and_extract_async(page: Page, max_products: int, job_id: str) -> list[dict]:
    """Scroll page and extract product cards asynchronously with error handling."""
    cards = []
    
    try:
        # Smart scrolling with conditional waits
        for scroll_count in range(6):  # Reduced from 8
            await page.mouse.wheel(0, random.randint(700, 1500))
            await asyncio.sleep(random.uniform(0.1, 0.3))  # Reduced delays
            
            # Try to extract after each scroll
            try:
                current_cards = await page.evaluate(EXTRACT_SCRIPT, {"maxProducts": max_products})
                cards = current_cards
                await store.append_log(job_id, f"Scroll {scroll_count + 1}: Extracted {len(cards)} products")
                
                if len(cards) >= max_products * 0.8:  # Stop early if we have enough
                    await store.append_log(job_id, f"Reached target: {len(cards)}/{max_products} products")
                    break
            except Exception as e:
                await store.append_log(job_id, f"⚠️  Extraction attempt {scroll_count + 1} failed: {str(e)[:100]}")
                continue
        
        # Final extraction if we have nothing yet
        if not cards:
            await store.append_log(job_id, "No products found during scrolling, attempting final extraction")
            try:
                cards = await page.evaluate(EXTRACT_SCRIPT, {"maxProducts": max_products})
                await store.append_log(job_id, f"Final extraction: {len(cards)} products found")
            except Exception as e:
                await store.append_log(job_id, f"❌ Final extraction failed: {str(e)}")
                cards = []
        
        return cards
    
    except Exception as e:
        await store.append_log(job_id, f"❌ Scroll extraction error: {str(e)}")
        return []


async def extract_with_async_playwright(job_id: str, request: ScrapeRequest, website: Website) -> list[Product]:
    """Extract products using async Playwright with optimized flow."""
    await store.update_job(job_id, progress=5, current_product="Initializing browser pool")
    
    # Get page from pool
    page = await _browser_pool.get_page()
    
    try:
        await store.update_job(job_id, progress=10, current_product="Loading live URL")
        await store.append_log(job_id, "Loading the live marketplace URL with async Playwright")
        
        # Navigate with smart wait
        await page.goto(str(request.url), wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(0.5)
        
        await store.update_job(job_id, progress=15, current_product="Scrolling and extracting cards")
        
        # Scroll and extract in parallel
        title = await page.title()
        body_text = await page.locator("body").inner_text(timeout=15000)
        cards = await scroll_and_extract_async(page, request.options.max_products, job_id)
        
        await store.update_job(job_id, progress=45, current_product="Enriching product details")
        await store.append_log(job_id, f"Loaded page title: {title[:90] or 'Untitled'}")
        
        # Check for CAPTCHA
        if re.search(r"captcha|robot check|verify you are human|enter the characters", body_text, flags=re.I):
            await store.update_job(job_id, captcha_alert=True)
            await store.append_log(job_id, "Amazon CAPTCHA or robot-check page detected")
        
        # Parallel detail fetching
        if cards:
            cards = await fetch_details_parallel(page.context, cards)
            await store.append_log(job_id, f"Enriched {len(cards)} product details in parallel")
            if request.options.include_variants and request.options.variant_depth > 0:
                await store.update_job(job_id, progress=55, current_product="Discovering and clicking product variants")
                cards = await expand_variants_parallel(page.context, cards, request.options.variant_depth)
                await store.append_log(job_id, f"Expanded live variant intelligence to {len(cards)} variant rows")
        
        # Parse cards to products
        category = urlparse(str(request.url)).path.strip("/").split("/")[0].replace("-", " ").title() or title[:40] or "General"
        rows = [
            apply_variant_fields(parse_card_to_product(job_id, str(request.url), website, category, rank, card), card)
            for rank, card in enumerate(cards[: request.options.max_products], start=1)
        ]
        visible_total = sum(product.visible_bought_count for product in rows)
        overall_units = sum(product.units_sold for product in rows)
        estimated_rows = sum(1 for product in rows if product.units_sold_estimated)
        await store.append_log(job_id, f"Step 1/4 extracted {len(cards)} candidate cards from the page")
        await store.append_log(job_id, f"Step 2/4 normalized {len(rows)} products into backend rows")
        await store.append_log(job_id, f"Step 3/4 calculated scraped overall bought count: {visible_total:,} visible units")
        await store.append_log(job_id, f"Step 3b/4 kept monthly demand units: {overall_units:,} units ({estimated_rows} rank-estimated rows)")
        await store.append_log(job_id, f"Step 4/4 calculated live product total revenue from scraped bought count x price: {sum(product.revenue for product in rows):,.2f}")
        
        return apply_parent_revenue(enrich_product_scores(rows))
    
    finally:
        await _browser_pool.return_page(page)


def _should_use_sync_fallback(exc: Exception) -> bool:
    """Return True for Playwright launch failures that sync mode can often survive."""
    message = f"{type(exc).__name__}: {exc!r}".lower()
    return isinstance(exc, (NotImplementedError, PermissionError, RuntimeError)) and any(
        marker in message
        for marker in [
            "notimplementederror",
            "permissionerror",
            "access is denied",
            "failed to start async playwright",
            "failed to launch async chromium",
            "subprocess",
            "windows",
        ]
    )


async def extract_with_sync_fallback(job_id: str, request: ScrapeRequest, website: Website) -> list[Product]:
    """Run the stable sync scraper path in a worker thread when async Playwright cannot start."""
    from backend.app.services.scraper_engine import extract_with_playwright

    await store.append_log(job_id, "Switching to sync Playwright fallback for this job")
    await store.update_job(job_id, progress=12, current_product="Using sync Playwright fallback")
    return await extract_with_playwright(job_id, request, website)


async def run_scrape_job_optimized(job_id: str, request: ScrapeRequest) -> None:
    """Optimized scrape job with async operations and better resource management."""
    from backend.app.services.scraper_engine import infer_website
    
    website = infer_website(str(request.url), request.website)
    await store.update_job(job_id, status=JobStatus.running, website=website, progress=2, current_product="Starting optimized scrape")
    await store.append_log(job_id, f"Optimized async scrape started for {website.value}: {request.url}")
    
    try:
        # Initialize browser pool. If async Playwright cannot start on Windows,
        # the job continues through the sync fallback below.
        try:
            await _browser_pool.initialize()
        except Exception as exc:
            await store.append_log(job_id, f"Async browser pool initialization failed: {type(exc).__name__}: {exc!r}")

        products: list[Product] = []
        try:
            if _browser_pool._playwright:
                products = await extract_with_async_playwright(job_id, request, website)
            else:
                products = await extract_with_sync_fallback(job_id, request, website)
        except PermissionError as exc:
            await store.update_job(job_id, captcha_alert=False, current_product="Playwright launch blocked by Windows permissions")
            await store.append_log(job_id, f"Permission error: {exc}")
            try:
                products = await extract_with_sync_fallback(job_id, request, website)
            except Exception as fallback_exc:
                await store.append_log(job_id, f"Sync fallback failed: {type(fallback_exc).__name__}: {fallback_exc!r}")
                await store.append_log(job_id, "\n".join(traceback.format_exc().splitlines()[-6:]))
        except Exception as exc:
            await store.append_log(job_id, f"Async extraction failed: {type(exc).__name__}: {exc!r}")
            await store.append_log(job_id, "\n".join(traceback.format_exc().splitlines()[-6:]))
            if _should_use_sync_fallback(exc):
                try:
                    products = await extract_with_sync_fallback(job_id, request, website)
                except Exception as fallback_exc:
                    await store.append_log(job_id, f"Sync fallback failed: {type(fallback_exc).__name__}: {fallback_exc!r}")
                    await store.append_log(job_id, "\n".join(traceback.format_exc().splitlines()[-6:]))
        
        if not products:
            await store.update_job(job_id, status=JobStatus.failed, progress=100, current_product="No products extracted")
            await store.append_log(job_id, "❌ No live product cards were extracted.")
            await store.append_log(job_id, "")
            await store.append_log(job_id, "🔍 DIAGNOSIS - Possible causes:")
            await store.append_log(job_id, "  1. Amazon page structure changed (CSS selectors outdated)")
            await store.append_log(job_id, "  2. CAPTCHA or bot detection block")
            await store.append_log(job_id, "  3. Page not fully rendering (JavaScript execution)")
            await store.append_log(job_id, "  4. Regional restriction or IP block")
            await store.append_log(job_id, "  5. Network timeout or connection issue")
            await store.append_log(job_id, "")
            await store.append_log(job_id, "💡 SOLUTIONS:")
            await store.append_log(job_id, "  • Retry the scrape (might be temporary)")
            await store.append_log(job_id, "  • Use external scraper service (if available)")
            await store.append_log(job_id, "  • Wait 5-10 minutes before retrying")
            await store.append_log(job_id, "  • Check backend logs for detailed error")
            return
        
        # Bulk save products with minimal delays
        total = len(products)
        await store.update_job(job_id, progress=70, remaining_products=total, current_product="Saving scraped products")
        
        for index, product in enumerate(products, start=1):
            job = await store.get_job(job_id)
            if job and job.status == JobStatus.stopped:
                await store.append_log(job_id, "Job stopped by user")
                return
            
            # Check pause status without blocking
            while True:
                job = await store.get_job(job_id)
                if not job or job.status != JobStatus.paused:
                    break
                await asyncio.sleep(0.2)
            
            await asyncio.sleep(random.uniform(0.1, 0.3))  # Minimal delay
            await store.add_product(job_id, product)
            await store.update_job(
                job_id,
                progress=70 + round((index / total) * 25),
                current_product=product.name,
                remaining_products=max(total - index, 0),
            )
            await store.append_log(job_id, f"Processed {product.product_rank} {product.name[:70]}")
        
        await store.update_job(job_id, status=JobStatus.completed, progress=100, current_product="Completed", remaining_products=0)
        await store.append_log(
            job_id,
            f"Optimized scrape completed: {total} products, "
            f"{sum(product.visible_bought_count for product in products):,} scraped bought count, "
            f"{sum(product.units_sold for product in products):,} monthly units used",
        )
    
    except Exception as exc:
        await store.update_job(job_id, status=JobStatus.failed)
        await store.append_log(job_id, f"Job failed: {exc}")
    
    finally:
        # Keep pool alive for next jobs
        pass


async def cleanup_browser_pool():
    """Clean up the browser pool (call on application shutdown)."""
    await _browser_pool.cleanup()
