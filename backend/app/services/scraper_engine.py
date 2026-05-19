from __future__ import annotations

import asyncio
import os
import random
import re
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

from app.schemas import JobStatus, Product, ScrapeRequest, Website
from app.services.analytics import enrich_product_scores
from app.services.store import store


RUPEE = "\u20b9"
MOJIBAKE_RUPEE = "\u00e2\u201a\u00b9"
PRICE_TOKEN = f"(?:{re.escape(RUPEE)}|{re.escape(MOJIBAKE_RUPEE)}|Rs\\.?|INR|\\$)"
BOUGHT_COUNT_PATTERN = r"\d[\d,.]*\s*(?:k|m|lakh|lac|l|crore|cr)?\+?\s*(?:bought|sold|purchased|orders?|units?|demand|sales)(?:\s+(?:in\s+)?(?:the\s+)?(?:past|last|per)\s+month)?"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BROWSER_PROFILE_DIR = PROJECT_ROOT / ".browser-profiles" / "flipkart-seller"


def infer_website(url: str, selected: Website) -> Website:
    host = urlparse(url).netloc.lower()
    detected = Website.auto
    for website in [Website.amazon, Website.flipkart, Website.myntra, Website.ajio, Website.ebay, Website.alibaba, Website.walmart]:
        if website.value in host:
            detected = website
            break
    if selected == Website.auto:
        return detected
    if detected != Website.auto and detected != selected:
        return detected
    return selected


def is_flipkart_seller_url(url: str) -> bool:
    parsed = urlparse(url)
    return "seller.flipkart.com" in parsed.netloc.lower()


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def first_match(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.I)
        if match:
            return clean_text(match.group(0))
    return ""


def number_from_text(text: str, fallback: float = 0) -> float:
    match = re.search(r"[\d,]+(?:\.\d+)?", text or "")
    if not match:
        return fallback
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return fallback


def parse_scaled_number(amount: str, suffix: str = "") -> int:
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
    parsed = int(number_from_text(value, fallback))
    return parsed or fallback


def parse_bought_count(text: str) -> int:
    clean = clean_text(text).lower().replace(",", "")
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(k|m|lakh|lac|l|crore|cr)?\+?\s*(?:bought|sold|purchased|orders?|units?|demand|sales)(?:\s+(?:in\s+)?(?:the\s+)?(?:past|last|per)\s+month)?",
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
    return round(max(price, 0) * max(visible_bought_count, 0), 2)


def category_from_url(url: str, title: str = "") -> str:
    parsed = urlparse(url)
    if "flipkart" in parsed.netloc.lower() and parsed.fragment:
        query = parsed.fragment.split("?", 1)[1] if "?" in parsed.fragment else ""
        vertical = parse_qs(query).get("selectedVertical", [""])[0]
        if vertical:
            return clean_text(vertical.replace("-", " ").replace("_", " ")).title()
    return parsed.path.strip("/").split("/")[0].replace("-", " ").title() or title[:40] or "General"


def parse_money_amount(text: str) -> float:
    match = re.search(rf"{PRICE_TOKEN}\s*([\d,]+(?:\.\d+)?)", text or "", flags=re.I)
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            return 0.0
    return number_from_text(text, 0.0)


def extract_discount_percentage(discount_text: str, price: float, original_price: float) -> float:
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
    parts = clean_text(name).split()
    return parts[0] if parts else ""


def discount_label(discount: float) -> str:
    if discount >= 35:
        return "High Discount"
    if discount >= 15:
        return "Medium Discount"
    if discount > 0:
        return "Low Discount"
    return "No Discount"


def apply_parent_revenue(products: list[Product]) -> list[Product]:
    totals: dict[str, float] = {}
    for product in products:
        key = product.parent_asin or product.id
        totals[key] = totals.get(key, 0) + product.revenue
    for product in products:
        product.parent_product_revenue = round(totals.get(product.parent_asin or product.id, product.revenue), 2)
    return products


NON_PRODUCT_TEXT_PATTERN = re.compile(
    r"\b("
    r"seller score|orders page|rewards?|dashboard|selection insights|"
    r"listing(?:s)? quality|keywords?|super seller|f-assured|preview|"
    r"what can i do|why are|how many|learn about|benefits of|"
    r"opera mobile|chrome desktop|firefox desktop|google chrome"
    r")\b",
    flags=re.I,
)


def _looks_like_product_url(value: str) -> bool:
    url = clean_text(value).lower()
    if not url:
        return False
    if "amazon." in url:
        return bool(re.search(r"/(?:dp|gp/product)/[a-z0-9]{10}", url, flags=re.I))
    if "flipkart." in url:
        return "/itm" in url or "/p/" in url or "pid=" in url
    return bool(re.search(r"/(?:product|item|itm|ip|p)/", url, flags=re.I))


def is_valid_product_card(card: dict, website: Website) -> bool:
    """Reject dashboard/help text that can otherwise be misread as product rows."""
    name = clean_text(card.get("name") or card.get("productName"))
    text = clean_text(card.get("text") or card.get("rawText") or name)
    link = clean_text(card.get("productUrl") or card.get("link") or card.get("url"))
    item_id = clean_text(card.get("id") or card.get("asin"))
    price = clean_text(card.get("price") or card.get("priceText"))
    bought = clean_text(card.get("boughtText"))
    rating = clean_text(card.get("rating"))
    reviews = clean_text(card.get("reviews"))

    if not name or name.lower().startswith(("which ", "why ", "how ", "what ", "learn ", "benefits ")):
        return False
    if website == Website.flipkart and NON_PRODUCT_TEXT_PATTERN.search(f"{name} {text}"):
        return False

    has_product_url = _looks_like_product_url(link)
    has_marketplace_id = bool(re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{5,}", item_id, flags=re.I))
    has_price = bool(price and parse_money_amount(price) > 0)
    has_demand = bool(bought and parse_bought_count(bought) > 0)
    has_social_proof = bool(rating or reviews)

    if website == Website.flipkart:
        return has_product_url or has_marketplace_id or has_price or has_demand
    return (has_product_url or has_marketplace_id) and (has_price or has_social_proof or has_demand or bool(name))


def filter_product_cards(cards: list[dict], website: Website) -> list[dict]:
    return [card for card in cards if is_valid_product_card(card, website)]


VISIBLE_CONTENT_SCRIPT = """
() => {
  const text = (document.body?.innerText || '').replace(/\\s+/g, ' ').trim();
  const usefulNodes = document.querySelectorAll('table, tbody tr, [role="row"], .ag-row, [data-testid], [class*="card" i], [class*="row" i]').length;
  return text.length > 40 || usefulNodes > 0;
}
"""


FRAME_SCORE_SCRIPT = """
() => {
  const text = (document.body?.innerText || '').replace(/\\s+/g, ' ').trim();
  const usefulNodes = document.querySelectorAll('table, tbody tr, [role="row"], .ag-row, [data-testid], [class*="card" i], [class*="row" i]').length;
  return { textLength: text.length, usefulNodes, score: text.length + usefulNodes * 250 };
}
"""


BODY_TEXT_SCRIPT = "() => document.body ? document.body.innerText : ''"


def frame_has_visible_content(frame) -> bool:
    try:
        return bool(frame.evaluate(VISIBLE_CONTENT_SCRIPT))
    except Exception:
        return False


def page_has_visible_content(page) -> bool:
    return any(
        frame_has_visible_content(frame)
        for frame in page.frames
        if "recaptcha" not in (frame.url or "").lower()
    )


def select_extraction_frame(page):
    best_frame = page.main_frame
    best_score = -1
    for frame in page.frames:
        if "recaptcha" in (frame.url or "").lower():
            continue
        try:
            score = frame.evaluate(FRAME_SCORE_SCRIPT)
            value = int(score.get("score") or 0)
        except Exception:
            value = 0
        if value > best_score:
            best_score = value
            best_frame = frame
    return best_frame


def page_has_recaptcha(page) -> bool:
    try:
        for frame in page.frames:
            if "recaptcha" in (frame.url or "").lower():
                return True
        return bool(page.locator("iframe[src*='recaptcha'], iframe[title*='recaptcha' i]").count())
    except Exception:
        return False


def wait_for_flipkart_seller_content(page, timeout_seconds: int) -> bool:
    deadline = time.time() + max(15, timeout_seconds)
    while time.time() < deadline:
        if page_has_visible_content(page):
            return True
        try:
            page.wait_for_timeout(1000)
        except Exception:
            time.sleep(1)
    return page_has_visible_content(page)


def parse_card_to_product(job_id: str, request_url: str, website: Website, category: str, rank: int, card: dict) -> Product:
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
        [BOUGHT_COUNT_PATTERN, r"\d[\d,.]*\s*(?:k|m|lakh|lac|l|crore|cr)?\+?\s*(?:units?|demand|sales)(?:\s+(?:per|last|past)\s+month)?"],
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


EXTRACT_SCRIPT = """
({ maxProducts }) => {
  const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const linesOf = (value) => (value || '').split('\\n').map((line) => clean(line)).filter(Boolean);
  const firstLine = (lines, predicate) => lines.find(predicate) || '';
  const absolute = (href) => {
    try { return href ? new URL(href, window.location.origin).href : ''; }
    catch { return ''; }
  };
  const getText = (element) => element ? clean(element.innerText || element.textContent || '') : '';
  const getAttr = (element, attr) => element ? clean(element.getAttribute(attr) || '') : '';
  const isPrice = (line) => line.includes('\\u20b9') || line.includes('\\u00e2\\u201a\\u00b9') || /\\b(?:rs\\.?|inr)\\s*[\\d,]+/i.test(line);
  const isBoughtCount = (line) => /\\d[\\d,.]*\\s*(?:[kKmM]|lakh|lac|L|crore|cr)?\\+?\\s*(?:bought|sold|purchased|orders?)(?:\\s+(?:in\\s+)?(?:the\\s+)?(?:past|last)\\s+month)?/i.test(line);
  const rows = [];
  const seen = new Set();
  const candidates = Array.from(document.querySelectorAll([
    'div.p13n-sc-uncoverable-faceout',
    'li.zg-carousel-general-faceout',
    'div[data-asin]',
    'li[data-asin]',
    'li[id]',
    '[data-asin]'
  ].join(',')));

  for (const node of candidates) {
    const rawText = node.innerText || '';
    const text = clean(rawText);
    const lines = linesOf(rawText);
    const linkNode = node.querySelector('a[href*="/dp/"], a[href*="/gp/product/"]');
    const link = absolute(linkNode ? (getAttr(linkNode, 'href') || linkNode.href || '') : '');
    const img = node.querySelector('img');
    const rawNodeId = clean(node.getAttribute('data-asin') || node.getAttribute('data-item-id') || node.getAttribute('id') || '');
    const idFromNode = /^[A-Z0-9]{10}$/.test(rawNodeId) ? rawNodeId : '';
    const asinFromLink = clean((link.match(/(?:dp|gp\\/product)\\/([A-Z0-9]{10})/) || [])[1] || '');
    const id = idFromNode || asinFromLink;
    const rank = clean(getText(node.querySelector('.zg-bdg-text, [class*="zg-bdg-text"]'))) || clean((text.match(/#\\d+/) || [])[0] || '');
    const name =
      clean(getText(node.querySelector("div[class*='p13n-sc-css-line-clamp']"))) ||
      clean(getText(node.querySelector("a.a-link-normal div"))) ||
      getAttr(img, 'alt') ||
      clean(getText(linkNode)) ||
      firstLine(lines, (line) => line.length > 10 && !line.startsWith('#') && !isPrice(line) && !/out of 5|stars|ratings?|reviews?/i.test(line));
    const price = firstLine(lines, (line) => isPrice(line) && !/mrp|m\\.r\\.p|save|coupon/i.test(line)) || firstLine(lines, isPrice);
    const ratingLine = firstLine(lines, (line) => /[0-5](?:\\.\\d+)?\\s*out of\\s*5/i.test(line));
    const rating = clean((ratingLine.match(/[0-5](?:\\.\\d+)?\\s*out of\\s*5(?:\\s*stars?)?/i) || [ratingLine])[0]);
    const ratingIndex = lines.indexOf(ratingLine);
    const reviews = clean((ratingLine.match(/out of\\s*5\\s*stars?\\s+([\\d,]+)/i) || [])[1] || '') ||
      (ratingIndex >= 0 ? firstLine(lines.slice(ratingIndex + 1, ratingIndex + 4), (line) => /^[\\d,]+$/.test(line)) : '');
    const boughtText = firstLine(lines, isBoughtCount);
    const discount = firstLine(lines, (line) => /-?\\d+(?:\\.\\d+)?\\s*%\\s*off/i.test(line));
    const key = id || link || name;
    if (!key || seen.has(key) || !name || !link) continue;
    seen.add(key);
    rows.push({
      text, rawText, name, productName: name, link, productUrl: link,
      img: getAttr(img, 'src') || getAttr(img, 'data-src') || '',
      imageUrl: getAttr(img, 'src') || getAttr(img, 'data-src') || '',
      id, asin: id, rank, price, rating, reviews, boughtText, discount
    });
    if (rows.length >= maxProducts) break;
  }

  for (const list of document.querySelectorAll('[data-client-recs-list]')) {
    if (rows.length >= maxProducts) break;
    try {
      const records = JSON.parse(getAttr(list, 'data-client-recs-list') || '[]');
      for (const record of records) {
        if (rows.length >= maxProducts) break;
        const id = clean(record?.id || '');
        if (!/^[A-Z0-9]{10}$/.test(id) || seen.has(id)) continue;
        const rankValue = clean(record?.metadataMap?.['render.zg.rank'] || '');
        const link = `${window.location.origin}/dp/${id}`;
        seen.add(id);
        rows.push({
          text: '', rawText: '', name: '', productName: '', link, productUrl: link,
          img: '', imageUrl: '', id, asin: id, rank: rankValue ? `#${rankValue}` : `#${rows.length + 1}`,
          price: '', rating: '', reviews: '', boughtText: '', discount: ''
        });
      }
    } catch {
      // Keep DOM card results if Amazon metadata is not valid JSON.
    }
  }

  if (!rows.length) {
    const pageText = document.body ? document.body.innerText : '';
    const pageLines = linesOf(pageText);
    const title = clean(getText(document.querySelector('#productTitle, span#title, h1')));
    const asinInput = document.querySelector('[name="ASIN"]');
    const asin = clean(getAttr(asinInput, 'value')) ||
      clean((window.location.href.match(/\\/(?:dp|gp\\/product)\\/([A-Z0-9]{10})/) || [])[1] || '');
    const image = clean(getAttr(document.querySelector('#landingImage, #imgTagWrapperId img'), 'src')) || '';
    const price = clean(getText(document.querySelector('#corePriceDisplay_desktop_feature_div .a-price .a-offscreen'))) ||
      clean(getText(document.querySelector('#priceblock_ourprice, #priceblock_dealprice, #priceblock_saleprice'))) ||
      firstLine(pageLines, (line) => isPrice(line) && !/mrp|m\\.r\\.p/i.test(line));
    const originalPrice = clean(getText(document.querySelector('.basisPrice .a-offscreen, .priceBlockStrikePriceString, .a-text-price .a-offscreen'))) ||
      clean((pageText.match(/M\\.R\\.P\\.?:?\\s*(?:\\u20b9|₹)\\s*[\\d,]+(?:\\.\\d+)?/i) || [])[0] || '').replace(/M\\.R\\.P\\.?:?\\s*/i, '');
    const discount = clean(getText(document.querySelector('.savingsPercentage'))) ||
      clean((pageText.match(/-?\\d+(?:\\.\\d+)?\\s*%/) || [])[0] || '');
    const rating = clean(getText(document.querySelector('#acrPopover .a-icon-alt'))) ||
      clean(getText(document.querySelector('[data-hook="rating-out-of-text"]'))) ||
      clean((pageText.match(/[0-5](?:\\.\\d+)?\\s*out of\\s*5(?:\\s*stars?)?/i) || [])[0] || '');
    const reviews = clean(getText(document.querySelector('#acrCustomerReviewText')).replace(/ratings?|reviews?/ig, '')) ||
      clean((pageText.match(/\\(([\\d,]+)\\)/) || [])[1] || '');
    const boughtText = clean(getText(document.querySelector('#social-proofing-faceout-title-tk_bought .a-text-bold'))) ||
      firstLine(pageLines, isBoughtCount);
    if (title) {
      rows.push({
        text: pageText, rawText: pageText, name: title, productName: title,
        link: window.location.href, productUrl: window.location.href,
        img: image, imageUrl: image, id: asin, asin, rank: '#1',
        price, originalPrice, discount, rating, reviews, boughtText
      });
    }
  }
  return rows;
}
"""


FLIPKART_EXTRACT_SCRIPT = """
({ maxProducts }) => {
  const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const linesOf = (value) => (value || '').split('\\n').map((line) => clean(line)).filter(Boolean);
  const firstLine = (lines, predicate) => lines.find(predicate) || '';
  const absolute = (href) => {
    try { return href ? new URL(href, window.location.origin).href : ''; }
    catch { return ''; }
  };
  const getText = (element) => element ? clean(element.innerText || element.textContent || '') : '';
  const getAttr = (element, attr) => element ? clean(element.getAttribute(attr) || '') : '';
  const isPrice = (line) => line.includes('\\u20b9') || line.includes('\\u00e2\\u201a\\u00b9') || /\\b(?:rs\\.?|inr)\\s*[\\d,]+/i.test(line);
  const metricPattern = /\\d[\\d,.]*\\s*(?:[kKmM]|lakh|lac|L|crore|cr)?\\+?\\s*(?:bought|sold|purchased|orders?|units?|demand|sales)(?:\\s+(?:in\\s+)?(?:the\\s+)?(?:past|last|per)\\s+month)?/i;
  const numericPattern = /\\d[\\d,.]*\\s*(?:[kKmM]|lakh|lac|L|crore|cr)?\\+?/i;
  const rows = [];
  const seen = new Set();

  const normalizeMetric = (value, label = 'demand units') => {
    const text = clean(value);
    if (!text) return '';
    if (metricPattern.test(text)) return clean((text.match(metricPattern) || [text])[0]);
    const number = clean((text.match(numericPattern) || [])[0] || '');
    return number ? `${number} ${label}` : '';
  };

  const textForHeader = (header, cells) => {
    const wanted = new RegExp(header, 'i');
    for (const cell of cells) {
      const value = clean(cell);
      if (wanted.test(value)) {
        const withoutLabel = clean(value.replace(wanted, ''));
        if (withoutLabel) return withoutLabel;
      }
    }
    return '';
  };

  const columnValue = (node, labels) => {
    const table = node.closest('table');
    const cells = Array.from(node.querySelectorAll('td, th, [role="gridcell"], [role="cell"]')).map(getText).filter(Boolean);
    if (!table || !cells.length) return '';
    const headers = Array.from(table.querySelectorAll('thead th, [role="columnheader"]')).map(getText).filter(Boolean);
    for (let i = 0; i < Math.min(headers.length, cells.length); i++) {
      if (labels.some((label) => headers[i].toLowerCase().includes(label))) {
        return cells[i];
      }
    }
    return '';
  };

  const nameFromLines = (lines) => firstLine(lines, (line) =>
    line.length >= 8 &&
    line.length <= 180 &&
    /[a-z]/i.test(line) &&
    !isPrice(line) &&
    !metricPattern.test(line) &&
    !/^(rank|fsn|sku|id|mrp|price|demand|orders|sales|units|brand|vertical|actions?|view|download|filter|sort)$/i.test(line)
  );

  const looksLikeProductUrl = (url) => /flipkart\\.com\\/(?:.*\\/itm|.*\\/p\\/|.*[?&]pid=)/i.test(url || '');
  const isDashboardHelpText = (value) => /\\b(?:seller score|orders page|rewards?|dashboard|selection insights|listing(?:s)? quality|keywords?|super seller|f-assured|preview|what can i do|why are|how many|learn about|benefits of|opera mobile|chrome desktop|firefox desktop|google chrome)\\b/i.test(value || '');
  const hasMarketplaceId = (value) => /^[A-Z0-9][A-Z0-9_-]{5,}$/i.test(clean(value || ''));

  const pushRow = (card) => {
    const name = clean(card.name || card.productName);
    if (!name || name.length < 3) return;
    const evidence = [
      looksLikeProductUrl(card.productUrl || card.link),
      hasMarketplaceId(card.id || card.asin),
      isPrice(card.price || ''),
      metricPattern.test(card.boughtText || '')
    ].some(Boolean);
    if (!evidence || isDashboardHelpText(`${name} ${card.text || ''}`)) return;
    const key = clean(card.id || card.asin || card.productUrl || `${name}:${card.price}:${card.boughtText}`);
    if (!key || seen.has(key)) return;
    seen.add(key);
    rows.push({
      text: clean(card.text),
      rawText: card.rawText || card.text || '',
      name,
      productName: name,
      link: clean(card.link || card.productUrl || ''),
      productUrl: clean(card.productUrl || card.link || ''),
      img: clean(card.img || card.imageUrl || ''),
      imageUrl: clean(card.imageUrl || card.img || ''),
      id: clean(card.id || card.asin || ''),
      asin: clean(card.asin || card.id || ''),
      rank: clean(card.rank || `#${rows.length + 1}`),
      price: clean(card.price || ''),
      originalPrice: clean(card.originalPrice || ''),
      discount: clean(card.discount || ''),
      rating: clean(card.rating || ''),
      reviews: clean(card.reviews || ''),
      boughtText: clean(card.boughtText || '')
    });
  };

  const candidates = Array.from(document.querySelectorAll([
    'tbody tr',
    'table tr',
    '[role="row"]',
    '.ag-row',
    '.ReactVirtualized__Table__row',
    '[class*="TableRow"]',
    '[class*="table-row"]',
    '[class*="grid-row"]',
    '[class*="opportunity"]',
    '[class*="Opportunity"]',
    '[class*="recommendation"]',
    '[class*="Recommendation"]',
    '[data-testid*="row"]',
    '[data-testid*="card"]'
  ].join(',')));

  for (const node of candidates) {
    if (rows.length >= maxProducts) break;
    const rawText = node.innerText || '';
    const text = clean(rawText);
    if (!text || text.length < 8 || text.length > 2500) continue;
    if (/login|password|sign\\s*in|otp|captcha/i.test(text)) continue;

    const lines = linesOf(rawText);
    const cellTexts = Array.from(node.querySelectorAll('td, th, [role="gridcell"], [role="cell"], [class*="cell"], [class*="Cell"]'))
      .map(getText)
      .filter((value, index, all) => value && all.indexOf(value) === index);
    const values = cellTexts.length >= 2 ? cellTexts : lines;
    const linkNode = node.querySelector('a[href]');
    const img = node.querySelector('img');
    const link = absolute(linkNode ? (getAttr(linkNode, 'href') || linkNode.href || '') : '');
    const id = clean(
      getAttr(node, 'data-fsn') ||
      getAttr(node, 'data-product-id') ||
      getAttr(node, 'data-listing-id') ||
      getAttr(node, 'data-id') ||
      ((text.match(/\\b(?:FSN|SKU|Product\\s*ID|Listing\\s*ID)\\s*:?\\s*([A-Z0-9_-]{6,})/i) || [])[1] || '') ||
      ((link.match(/\\/(?:itm|p)\\/([^/?#]+)/i) || [])[1] || '')
    );
    const rank = clean((text.match(/#\\s*\\d+/) || [])[0] || '');
    const explicitName =
      clean(getText(node.querySelector('[class*="product"][class*="name" i], [class*="title" i], [data-testid*="name"], [data-testid*="title"]'))) ||
      clean(getAttr(node, 'title')) ||
      clean(getAttr(node, 'aria-label')) ||
      getAttr(img, 'alt') ||
      clean(getText(linkNode));
    const name = explicitName || nameFromLines(values) || nameFromLines(lines);
    const price =
      columnValue(node, ['price', 'asp', 'selling']) ||
      textForHeader('(?:price|asp|selling price)', values) ||
      firstLine(values, (line) => isPrice(line) && !/mrp|list|original/i.test(line)) ||
      firstLine(lines, (line) => isPrice(line) && !/mrp|list|original/i.test(line));
    const originalPrice =
      columnValue(node, ['mrp', 'list', 'original']) ||
      textForHeader('(?:mrp|list price|original price)', values) ||
      firstLine(values, (line) => isPrice(line) && /mrp|list|original/i.test(line));
    const discount =
      columnValue(node, ['discount']) ||
      firstLine(values, (line) => /-?\\d+(?:\\.\\d+)?\\s*%\\s*(?:off)?/i.test(line));
    const demand =
      columnValue(node, ['demand', 'orders', 'sales', 'units']) ||
      textForHeader('(?:monthly demand|demand|orders|sales|units|potential sales)', values) ||
      firstLine(values, (line) => metricPattern.test(line)) ||
      firstLine(lines, (line) => metricPattern.test(line));
    const rating = firstLine(values, (line) => /[0-5](?:\\.\\d+)?\\s*(?:out of\\s*5|stars?)/i.test(line));
    const reviews = firstLine(values, (line) => /[\\d,]+\\s*(?:ratings?|reviews?)/i.test(line));

    if (!name) continue;
    if (!id && !looksLikeProductUrl(link) && !price && !demand) continue;
    pushRow({
      text,
      rawText,
      name,
      productName: name,
      link,
      productUrl: link,
      img: getAttr(img, 'src') || getAttr(img, 'data-src') || '',
      imageUrl: getAttr(img, 'src') || getAttr(img, 'data-src') || '',
      id,
      asin: id,
      rank,
      price,
      originalPrice,
      discount,
      rating,
      reviews,
      boughtText: normalizeMetric(demand)
    });
  }

  const visit = (value, depth = 0) => {
    if (rows.length >= maxProducts || depth > 5 || !value || typeof value !== 'object') return;
    if (Array.isArray(value)) {
      value.forEach((item) => visit(item, depth + 1));
      return;
    }
    const keys = Object.keys(value);
    const pick = (...names) => {
      for (const name of names) {
        const key = keys.find((candidate) => candidate.toLowerCase() === name.toLowerCase());
        if (key && value[key] != null && typeof value[key] !== 'object') return clean(String(value[key]));
      }
      return '';
    };
    const name = pick('productName', 'productTitle', 'title', 'name', 'listingTitle');
    if (name) {
      const id = pick('fsn', 'productId', 'listingId', 'sku', 'id');
      const price = pick('sellingPrice', 'price', 'asp', 'listingPrice');
      const originalPrice = pick('mrp', 'originalPrice', 'listPrice');
      const demand = pick('demand', 'monthlyDemand', 'orders', 'orderCount', 'sales', 'units', 'unitsSold', 'potentialSales');
      pushRow({
        text: JSON.stringify(value).slice(0, 2000),
        rawText: JSON.stringify(value).slice(0, 2000),
        name,
        productName: name,
        id,
        asin: id,
        price: isPrice(price) ? price : (price ? `Rs. ${price}` : ''),
        originalPrice: isPrice(originalPrice) ? originalPrice : (originalPrice ? `Rs. ${originalPrice}` : ''),
        boughtText: normalizeMetric(demand)
      });
    }
    for (const key of keys) visit(value[key], depth + 1);
  };

  const parseMaybeJson = (value) => {
    try { visit(JSON.parse(value)); } catch {}
  };
  Array.from(document.querySelectorAll('script[type="application/json"], script#__NEXT_DATA__')).forEach((script) => parseMaybeJson(script.textContent || ''));
  try {
    for (let i = 0; i < localStorage.length; i++) parseMaybeJson(localStorage.getItem(localStorage.key(i)) || '');
    for (let i = 0; i < sessionStorage.length; i++) parseMaybeJson(sessionStorage.getItem(sessionStorage.key(i)) || '');
  } catch {}

  return rows.slice(0, maxProducts);
}
"""


DETAIL_SCRIPT = """
() => {
  const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const linesOf = (value) => (value || '').split('\\n').map((line) => clean(line)).filter(Boolean);
  const firstLine = (lines, predicate) => lines.find(predicate) || '';
  const getText = (element) => element ? clean(element.innerText || element.textContent || '') : '';
  const getAttr = (element, attr) => element ? clean(element.getAttribute(attr) || '') : '';
  const boughtPattern = /\\d[\\d,.]*\\s*(?:[kKmM]|lakh|lac|L|crore|cr)?\\+?\\s*(?:bought|sold|purchased|orders?)(?:\\s+(?:in\\s+)?(?:the\\s+)?(?:past|last)\\s+month)?/i;
  const boughtMatch = (value) => clean(((value || '').match(boughtPattern) || [])[0] || '');
  const pageText = document.body ? document.body.innerText : '';
  const pageLines = linesOf(pageText);
  const isPrice = (line) => line.includes('\\u20b9') || line.includes('\\u00e2\\u201a\\u00b9') || /\\b(?:rs\\.?|inr)\\s*[\\d,]+/i.test(line);
  const isBoughtCount = (line) => /\\d[\\d,.]*\\s*(?:[kKmM]|lakh|lac|L|crore|cr)?\\+?\\s*(?:bought|sold|purchased|orders?)(?:\\s+(?:in\\s+)?(?:the\\s+)?(?:past|last)\\s+month)?/i.test(line);
  const title = clean(getText(document.querySelector('#productTitle, span#title, h1')));
  const asinInput = document.querySelector('[name="ASIN"]');
  const asin = clean(getAttr(asinInput, 'value')) ||
    clean((window.location.href.match(/\\/(?:dp|gp\\/product)\\/([A-Z0-9]{10})/) || [])[1] || '');
  const image = clean(getAttr(document.querySelector('#landingImage, #imgTagWrapperId img'), 'src')) || '';
  const price = clean(getText(document.querySelector('#corePriceDisplay_desktop_feature_div .a-price .a-offscreen'))) ||
    clean(getText(document.querySelector('#priceblock_ourprice, #priceblock_dealprice, #priceblock_saleprice'))) ||
    firstLine(pageLines, (line) => isPrice(line) && !/mrp|m\\.r\\.p/i.test(line));
  const originalPrice = clean(getText(document.querySelector('.basisPrice .a-offscreen, .priceBlockStrikePriceString, .a-text-price .a-offscreen'))) ||
    clean((pageText.match(/M\\.R\\.P\\.?:?\\s*(?:\\u20b9|₹)\\s*[\\d,]+(?:\\.\\d+)?/i) || [])[0] || '').replace(/M\\.R\\.P\\.?:?\\s*/i, '');
  const discount = clean(getText(document.querySelector('.savingsPercentage'))) ||
    clean((pageText.match(/-?\\d+(?:\\.\\d+)?\\s*%/) || [])[0] || '');
  const rating = clean(getText(document.querySelector('#acrPopover .a-icon-alt'))) ||
    clean(getText(document.querySelector('[data-hook="rating-out-of-text"]'))) ||
    clean((pageText.match(/[0-5](?:\\.\\d+)?\\s*out of\\s*5(?:\\s*stars?)?/i) || [])[0] || '');
  const reviews = clean(getText(document.querySelector('#acrCustomerReviewText')).replace(/ratings?|reviews?/ig, '')) ||
    clean((pageText.match(/\\(([\\d,]+)\\)/) || [])[1] || '');
  const socialProof = document.querySelector('#social-proofing-faceout-title-tk_bought .a-text-bold, #social-proofing-faceout-title-tk_bought, #social-proofing-faceout-title-tk_bought span');
  const boughtElement = Array.from(document.querySelectorAll('span, div, p')).find(el => boughtPattern.test(el.innerText || ''));
  const boughtText = boughtMatch(getText(socialProof)) ||
    boughtMatch(getText(boughtElement)) ||
    firstLine(pageLines, isBoughtCount);
  return {
    text: pageText,
    rawText: pageText,
    name: title,
    productName: title,
    link: window.location.href,
    productUrl: window.location.href,
    img: image,
    imageUrl: image,
    id: asin,
    asin,
    price,
    originalPrice,
    discount,
    rating,
    reviews,
    boughtText
  };
}
"""


def extract_cards_sync(request: ScrapeRequest) -> tuple[str, str, list[dict]]:
    website = infer_website(str(request.url), request.website)
    request_url = str(request.url)
    use_flipkart_profile = website == Website.flipkart and is_flipkart_seller_url(request_url)
    profile_dir = Path(os.getenv("SCRAPER_FLIPKART_PROFILE_DIR", str(DEFAULT_BROWSER_PROFILE_DIR)))
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        user_agent = random.choice(
            [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            ]
        )
        if use_flipkart_profile:
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                headless=env_flag("SCRAPER_FLIPKART_HEADLESS", False),
                slow_mo=80,
                viewport={"width": 1440, "height": 1000},
                user_agent=user_agent,
                locale="en-IN",
                timezone_id="Asia/Kolkata",
                extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
                args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
            )
        else:
            browser = playwright.chromium.launch(
                headless=request.options.headless,
                slow_mo=60,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                user_agent=user_agent,
                locale="en-IN",
                timezone_id="Asia/Kolkata",
                extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
            )
        page = context.pages[0] if use_flipkart_profile and context.pages else context.new_page()
        try:
            page.goto(request_url, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            if website == Website.flipkart:
                if use_flipkart_profile and not page_has_visible_content(page):
                    wait_for_flipkart_seller_content(page, int(os.getenv("SCRAPER_FLIPKART_LOGIN_WAIT_SECONDS", "180")))
                time.sleep(3)
            for _ in range(8):
                page.mouse.wheel(0, random.randint(900, 1800))
                time.sleep(random.uniform(0.2, 0.55))
            title = page.title()
            body_text = page.locator("body").inner_text(timeout=15000)
            extract_script = FLIPKART_EXTRACT_SCRIPT if website == Website.flipkart else EXTRACT_SCRIPT
            cards = page.evaluate(extract_script, {"maxProducts": request.options.max_products})
            if website == Website.flipkart and not cards:
                time.sleep(4)
                cards = page.evaluate(extract_script, {"maxProducts": request.options.max_products})
            cards = filter_product_cards(list(cards), website)
            for index, card in enumerate(list(cards)):
                if website == Website.flipkart:
                    continue
                product_url = clean_text(card.get("productUrl") or card.get("link"))
                needs_detail = not card.get("boughtText") or not card.get("originalPrice") or not card.get("discount")
                if not product_url or not needs_detail:
                    continue
                try:
                    page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
                    time.sleep(random.uniform(0.8, 1.4))
                    detail = page.evaluate(DETAIL_SCRIPT)
                    merged = {**card}
                    for key, value in detail.items():
                        if value and (key in {"boughtText", "originalPrice", "discount"} or not merged.get(key)):
                            merged[key] = value
                    merged["rank"] = card.get("rank") or f"#{index + 1}"
                    cards[index] = merged
                except Exception:
                    continue
            return title, body_text, cards
        finally:
            context.close()
            browser.close()


async def extract_with_playwright(job_id: str, request: ScrapeRequest, website: Website) -> list[Product]:
    await store.update_job(job_id, progress=8, current_product="Opening browser and loading live URL")
    await store.append_log(job_id, "Opening Chromium and loading the live marketplace URL")
    await store.update_job(job_id, progress=18, current_product="Scrolling page and collecting product cards")
    title, text, cards = await asyncio.to_thread(extract_cards_sync, request)
    await store.update_job(job_id, progress=48, current_product="Parsing product cards and detail pages")
    await store.append_log(job_id, f"Loaded page title: {title[:90] or 'Untitled'}")
    if re.search(r"captcha|robot check|verify you are human|enter the characters", text, flags=re.I):
        await store.update_job(job_id, captcha_alert=True)
        await store.append_log(job_id, f"{website.value.title()} CAPTCHA or robot-check page detected")
    await store.append_log(job_id, f"Browser extracted {len(cards)} candidate product cards")
    if cards and website == Website.flipkart:
        await store.append_log(job_id, "Parsed validated Flipkart product/listing rows from the live table/grid")
    elif cards:
        await store.append_log(job_id, "Detail-page enrichment completed for price, discount, bought count, and reviews")
    await store.update_job(job_id, progress=62, current_product="Calculating bought counts and revenue")
    category = category_from_url(str(request.url), title)
    rows = [
        parse_card_to_product(job_id, str(request.url), website, category, rank, card)
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


async def run_scrape_job(job_id: str, request: ScrapeRequest) -> None:
    website = infer_website(str(request.url), request.website)
    await store.update_job(job_id, status=JobStatus.running, website=website, progress=2, current_product="Starting live scrape")
    await store.append_log(job_id, f"Live scrape started for {website.value}: {request.url}")
    try:
        products: list[Product] = []
        try:
            products = await extract_with_playwright(job_id, request, website)
        except PermissionError as exc:
            await store.update_job(job_id, captcha_alert=False, current_product="Playwright launch blocked by Windows permissions")
            await store.append_log(
                job_id,
                "Playwright launch was blocked by Windows permissions. Start the backend from a normal PowerShell session, run it as administrator, or use the External service option.",
            )
            await store.append_log(job_id, f"Permission detail: {exc!r}")
        except Exception as exc:
            await store.append_log(job_id, f"Playwright extraction failed: {type(exc).__name__}: {exc!r}")
        if not products:
            await store.update_job(job_id, status=JobStatus.failed, progress=100, current_product=f"No live {website.value} products extracted")
            await store.append_log(
                job_id,
                f"No live product rows were extracted. {website.value.title()} may have shown a login prompt, CAPTCHA, empty dashboard, or blocked the browser session.",
            )
            return

        total = len(products)
        await store.update_job(job_id, progress=70, remaining_products=total, current_product="Saving scraped products")
        for index, product in enumerate(products, start=1):
            job = await store.get_job(job_id)
            if job and job.status == JobStatus.stopped:
                await store.append_log(job_id, "Job stopped by user")
                return
            while True:
                job = await store.get_job(job_id)
                if not job or job.status != JobStatus.paused:
                    break
                await asyncio.sleep(0.5)
            await asyncio.sleep(random.uniform(0.25, 0.7))
            await store.add_product(job_id, product)
            await store.update_job(
                job_id,
                progress=70 + round((index / total) * 25),
                current_product=product.name,
                remaining_products=max(total - index, 0),
            )
            await store.append_log(job_id, f"Processed live row {product.product_rank} {product.name[:70]}")
        await store.update_job(job_id, status=JobStatus.completed, progress=100, current_product="Completed", remaining_products=0)
        await store.append_log(
            job_id,
            f"Live scrape completed: {total} products, "
            f"{sum(product.visible_bought_count for product in products):,} scraped bought count, "
            f"{sum(product.units_sold for product in products):,} monthly units used, analytics export is ready",
        )
    except Exception as exc:
        await store.update_job(job_id, status=JobStatus.failed)
        await store.append_log(job_id, f"Job failed: {exc}")
