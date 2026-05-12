"""
Optimized async scraper with enhanced performance.
Incorporates:
- Smart waits (condition-based instead of fixed delays)
- Retry with backoff
- Parallel extraction
- Batch processing
- Caching
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from playwright.async_api import Page, BrowserContext
from app.schemas import JobStatus, Product, ScrapeRequest, Website
from app.services.store import store
from app.services.cache_manager import (
    get_cache,
    get_duplicate_detector,
    cache_product_list,
    get_cached_products,
    invalidate_url_cache,
)
from app.services.retry_engine import (
    get_retry_engine,
    RetryConfig,
    RetryStrategy,
)
from app.services.smart_wait import get_smart_wait_engine
from app.services.async_scraper import (
    EXTRACT_SCRIPT,
    DETAIL_SCRIPT,
    VARIANT_SCRIPT,
    parse_card_to_product,
    apply_variant_fields,
    apply_parent_revenue,
    infer_variant_type,
    clean_text,
)
from app.services.analytics import enrich_product_scores
from app.services.scraper_engine import infer_website
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class OptimizedScraper:
    """Enhanced scraper with all performance optimizations."""
    
    def __init__(self):
        self.cache = get_cache()
        self.duplicate_detector = get_duplicate_detector()
        self.retry_engine = get_retry_engine()
        self.smart_wait = get_smart_wait_engine()
        self.extraction_stats = {}
    
    async def extract_with_caching(
        self,
        page: Page,
        url: str,
        job_id: str,
        max_products: int = 24,
        force_refresh: bool = False,
    ) -> list[dict]:
        """
        Extract products with caching layer.
        
        Returns:
            List of product card dicts
        """
        # Check cache first
        if not force_refresh:
            cached = await get_cached_products(url)
            if cached:
                await store.append_log(job_id, f"✅ Cache hit! Using {len(cached)} cached products")
                return cached
        
        # Not in cache or force refresh - extract fresh
        cards = await self._extract_fresh(page, url, job_id, max_products)
        
        # Cache the results
        if cards:
            await cache_product_list(url, cards, ttl_seconds=3600)
            await store.append_log(job_id, f"💾 Cached {len(cards)} products for future use")
        
        return cards
    
    async def _extract_fresh(
        self,
        page: Page,
        url: str,
        job_id: str,
        max_products: int,
    ) -> list[dict]:
        """Extract products freshly from page with smart scrolling."""
        await store.update_job(job_id, progress=15, current_product="Smart scrolling and extracting")
        
        cards = []
        await store.append_log(job_id, "Starting smart extraction with condition-based waits...")
        
        try:
            # Wait for product cards to appear
            cards_found = await self.smart_wait.wait_for_product_cards(page, min_cards=1)
            if not cards_found:
                await store.append_log(job_id, "⚠️ No product cards found in initial load")
            
            # Smart scroll to load more products
            await store.append_log(job_id, "Scrolling page with intelligent waits...")
            scroll_height = await self.smart_wait.smart_scroll_to_load(
                page,
                max_scrolls=6,
                timeout_ms=30000,
            )
            
            await store.append_log(job_id, f"Scrolled to height: {scroll_height}px")
            
            # Extract all visible products
            cards = await page.evaluate(EXTRACT_SCRIPT, {"maxProducts": max_products})
            await store.append_log(job_id, f"Extracted {len(cards)} product cards from page")
            
            # Deduplicate using hashing
            unique_cards = await self._deduplicate_cards(cards)
            await store.append_log(job_id, f"After deduplication: {len(unique_cards)} unique cards")
            
            return unique_cards[:max_products]
        
        except Exception as e:
            logger.error(f"Extraction error: {e}")
            await store.append_log(job_id, f"❌ Extraction error: {str(e)[:100]}")
            return []
    
    async def _deduplicate_cards(self, cards: list[dict]) -> list[dict]:
        """Remove duplicate cards based on product hash."""
        seen = set()
        unique = []
        
        for card in cards:
            # Create simple hash
            card_id = card.get("id") or card.get("link")
            if card_id and card_id not in seen:
                seen.add(card_id)
                unique.append(card)
        
        return unique
    
    async def fetch_product_details_parallel(
        self,
        context: BrowserContext,
        cards: list[dict],
        job_id: str,
        batch_size: int = 4,
    ) -> list[dict]:
        """Fetch details for multiple products in parallel batches with retry."""
        if not cards:
            return cards
        
        await store.append_log(job_id, f"Fetching details for {len(cards)} products in parallel...")
        
        # Filter cards that need detail fetch
        needs_detail = [
            (i, card) for i, card in enumerate(cards)
            if (not card.get("boughtText") or not card.get("originalPrice"))
            and card.get("productUrl")
        ]
        
        if not needs_detail:
            await store.append_log(job_id, "All cards have required details, skipping detail fetch")
            return cards
        
        # Process in batches with retry
        processed = 0
        for batch_start in range(0, len(needs_detail), batch_size):
            batch = needs_detail[batch_start:batch_start + batch_size]
            
            tasks = [
                self._fetch_product_detail_with_retry(context, card.get("productUrl"), card, job_id)
                for _, card in batch
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for (idx, _), result in zip(batch, results):
                if isinstance(result, dict):
                    cards[idx] = result
                    processed += 1
            
            progress = 45 + (processed / len(needs_detail) * 10)
            await store.update_job(job_id, progress=int(progress))
        
        await store.append_log(job_id, f"✅ Enriched {processed}/{len(needs_detail)} product details")
        return cards
    
    async def _fetch_product_detail_with_retry(
        self,
        context: BrowserContext,
        product_url: str,
        card: dict,
        job_id: str,
    ) -> dict:
        """Fetch product detail with automatic retry."""
        config = RetryConfig(
            max_attempts=2,
            initial_delay_ms=300,
            strategy=RetryStrategy.LINEAR,
        )
        
        async def fetch():
            page = None
            try:
                page = await context.new_page()
                await self.smart_wait.wait_for_dynamic_content(page)
                await page.goto(product_url, wait_until="domcontentloaded", timeout=45000)
                
                # Wait for price elements
                await self.smart_wait.wait_for_price_elements(page)
                
                detail = await page.evaluate(DETAIL_SCRIPT)
                
                merged = {**card}
                for key, value in detail.items():
                    if value and (key in {"boughtText", "originalPrice", "discount"} or not merged.get(key)):
                        merged[key] = value
                
                return merged
            
            except Exception as e:
                logger.debug(f"Detail fetch failed: {e}")
                return card
            
            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass
        
        return await self.retry_engine.execute_with_retry(
            fetch,
            circuit_key=f"detail_{product_url[:30]}",
            config=config,
        )
    
    async def expand_variants_parallel(
        self,
        context: BrowserContext,
        cards: list[dict],
        max_variants: int,
        job_id: str,
        batch_size: int = 2,
    ) -> list[dict]:
        """Expand product variants with parallel processing and retry."""
        if max_variants <= 0 or not cards:
            return cards
        
        await store.append_log(job_id, f"Discovering variants for {len(cards)} products...")
        
        expanded = []
        processed = 0
        
        for batch_start in range(0, len(cards), batch_size):
            batch = cards[batch_start:batch_start + batch_size]
            
            tasks = [
                self._expand_variants_with_retry(context, card, max_variants, job_id)
                for card in batch
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, list):
                    expanded.extend(result)
                    processed += len(result)
            
            progress = 55 + (batch_start / len(cards) * 10)
            await store.update_job(job_id, progress=int(progress))
        
        await store.append_log(job_id, f"✅ Expanded to {processed} variant rows")
        return expanded
    
    async def _expand_variants_with_retry(
        self,
        context: BrowserContext,
        card: dict,
        max_variants: int,
        job_id: str,
    ) -> list[dict]:
        """Expand variants for single product with retry."""
        config = RetryConfig(
            max_attempts=2,
            initial_delay_ms=500,
            strategy=RetryStrategy.LINEAR,
        )
        
        async def expand():
            page = None
            try:
                page = await context.new_page()
                await page.goto(card.get("productUrl", ""), wait_until="domcontentloaded", timeout=45000)
                await self.smart_wait.wait_for_dynamic_content(page)
                
                discovery = await page.evaluate(VARIANT_SCRIPT, {"maxVariants": max_variants})
                variants = discovery.get("variants") or []
                
                if not variants:
                    return [card]
                
                # Click variants and capture state
                rows = []
                for variant in variants[:max_variants]:
                    try:
                        selector = f'[data-asin="{variant.get("asin")}"]' if variant.get("asin") else f'text="{str(variant.get("text", ""))[:80]}"'
                        
                        await page.locator(selector).first.click(timeout=5000)
                        await asyncio.sleep(0.5)
                        
                        # Wait for element to update
                        await self.smart_wait.wait_for_element_to_update(
                            page,
                            "#priceblock_ourprice",
                            card.get("price", ""),
                            timeout_ms=8000,
                        )
                        
                        detail = await page.evaluate(DETAIL_SCRIPT)
                        rows.append({
                            **card,
                            **{k: v for k, v in detail.items() if v},
                            "variantName": clean_text(variant.get("text")) or "Detected variant",
                            "variantGroup": clean_text(variant.get("group")),
                        })
                    
                    except Exception:
                        rows.append({
                            **card,
                            "variantName": clean_text(variant.get("text")) or "Detected variant",
                        })
                
                return rows or [card]
            
            except Exception:
                return [card]
            
            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass
        
        return await self.retry_engine.execute_with_retry(
            expand,
            circuit_key=f"variant_{card.get('id', 'unknown')}",
            config=config,
        )
    
    async def parse_cards_to_products(
        self,
        cards: list[dict],
        job_id: str,
        request_url: str,
        website: Website,
        job_start_time: float,
    ) -> list[Product]:
        """Convert card dicts to Product objects."""
        title = cards[0].get("pageTitle", "") if cards else ""
        category = urlparse(request_url).path.strip("/").split("/")[0].replace("-", " ").title() or title[:40] or "General"
        
        products = []
        for rank, card in enumerate(cards, start=1):
            try:
                product = parse_card_to_product(job_id, request_url, website, category, rank, card)
                product = apply_variant_fields(product, card)
                products.append(product)
            except Exception as e:
                logger.error(f"Product parsing error at rank {rank}: {e}")
                await store.append_log(job_id, f"⚠️ Error parsing rank {rank}: {str(e)[:50]}")
        
        # Apply analytics
        products = apply_parent_revenue(enrich_product_scores(products))
        
        # Log statistics
        visible_total = sum(p.visible_bought_count for p in products)
        overall_units = sum(p.units_sold for p in products)
        revenue_total = sum(p.revenue for p in products)
        elapsed = time.time() - job_start_time
        
        await store.append_log(job_id, f"📊 Extracted {len(products)} products in {elapsed:.1f}s")
        await store.append_log(job_id, f"💰 Total revenue from visible bought: ₹{revenue_total:,.2f}")
        await store.append_log(job_id, f"📈 Overall units: {overall_units:,}")
        
        return products


# Global optimized scraper instance
_optimized_scraper = OptimizedScraper()


def get_optimized_scraper() -> OptimizedScraper:
    """Get global optimized scraper."""
    return _optimized_scraper
