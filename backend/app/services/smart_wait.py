"""
Smart wait strategies for Playwright - replace fixed delays with condition-based waits.
Features:
- Wait for element visibility
- Wait for dynamic content load
- Smart scroll detection
- Custom condition waits
- Timeout handling
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional, Any
from playwright.async_api import Page, expect, TimeoutError as PlaywrightTimeoutError

import logging

logger = logging.getLogger(__name__)


class SmartWaitConfig:
    """Configuration for smart waits."""
    
    def __init__(
        self,
        element_timeout_ms: int = 15000,
        load_state_timeout_ms: int = 30000,
        idle_timeout_ms: int = 5000,
        custom_condition_timeout_ms: int = 20000,
    ):
        self.element_timeout_ms = element_timeout_ms
        self.load_state_timeout_ms = load_state_timeout_ms
        self.idle_timeout_ms = idle_timeout_ms
        self.custom_condition_timeout_ms = custom_condition_timeout_ms


class SmartWaitEngine:
    """Intelligent wait strategies instead of fixed delays."""
    
    def __init__(self, config: Optional[SmartWaitConfig] = None):
        self.config = config or SmartWaitConfig()
    
    async def wait_for_product_cards(
        self,
        page: Page,
        selector: str = "div.p13n-sc-uncoverable-faceout, li.zg-carousel-general-faceout, div[data-asin]",
        min_cards: int = 3,
        timeout_ms: Optional[int] = None,
    ) -> bool:
        """
        Wait for product cards to appear on page.
        
        Returns:
            True if cards found within timeout, False otherwise
        """
        timeout = timeout_ms or self.config.element_timeout_ms
        start_time = time.time()
        
        try:
            while time.time() - start_time < timeout / 1000:
                try:
                    cards = await page.query_selector_all(selector)
                    visible_cards = []
                    
                    for card in cards:
                        is_visible = await card.is_visible()
                        if is_visible:
                            visible_cards.append(card)
                    
                    if len(visible_cards) >= min_cards:
                        logger.info(f"Found {len(visible_cards)} product cards")
                        return True
                
                except Exception:
                    pass
                
                await asyncio.sleep(0.3)
            
            return False
        
        except Exception as e:
            logger.error(f"Error waiting for product cards: {e}")
            return False
    
    async def wait_for_price_elements(
        self,
        page: Page,
        timeout_ms: Optional[int] = None,
    ) -> bool:
        """Wait for price elements to be visible."""
        timeout = timeout_ms or self.config.element_timeout_ms
        
        try:
            # Try multiple price selectors
            selectors = [
                "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
                "#priceblock_ourprice",
                "#priceblock_dealprice",
                "[data-a-color='danger']",
                "span:has-text('₹')",
            ]
            
            for selector in selectors:
                try:
                    await page.wait_for_selector(selector, timeout=timeout)
                    return True
                except PlaywrightTimeoutError:
                    continue
            
            return False
        
        except Exception as e:
            logger.error(f"Error waiting for price elements: {e}")
            return False
    
    async def wait_for_dynamic_content(
        self,
        page: Page,
        timeout_ms: Optional[int] = None,
    ) -> bool:
        """Wait for dynamic content to load (images, reviews, etc.)."""
        timeout = timeout_ms or self.config.load_state_timeout_ms
        
        try:
            # Wait for main load states
            await page.wait_for_load_state("domcontentloaded", timeout=timeout)
            
            # Wait for network idle
            try:
                await page.wait_for_load_state("networkidle", timeout=min(timeout, 10000))
            except PlaywrightTimeoutError:
                # networkidle might not complete, that's okay
                pass
            
            return True
        
        except Exception as e:
            logger.error(f"Error waiting for dynamic content: {e}")
            return False
    
    async def wait_for_scrollable_content(
        self,
        page: Page,
        initial_height: Optional[int] = None,
        timeout_ms: Optional[int] = None,
    ) -> int:
        """
        Wait for scrollable content to appear after scroll.
        
        Returns:
            Height of scrollable content, or 0 if timeout
        """
        timeout = timeout_ms or self.config.idle_timeout_ms
        start_time = time.time()
        
        try:
            last_height = initial_height or await page.evaluate("document.documentElement.scrollHeight")
            
            while time.time() - start_time < timeout / 1000:
                current_height = await page.evaluate("document.documentElement.scrollHeight")
                
                if current_height > last_height:
                    logger.info(f"Scrollable content detected: {current_height}px")
                    return current_height
                
                await asyncio.sleep(0.2)
            
            return 0
        
        except Exception as e:
            logger.error(f"Error waiting for scrollable content: {e}")
            return 0
    
    async def wait_for_element_to_update(
        self,
        page: Page,
        selector: str,
        initial_text: str,
        timeout_ms: Optional[int] = None,
    ) -> bool:
        """
        Wait for element text to change (useful for variant clicks).
        
        Returns:
            True if element text changed within timeout
        """
        timeout = timeout_ms or self.config.custom_condition_timeout_ms
        start_time = time.time()
        
        try:
            while time.time() - start_time < timeout / 1000:
                try:
                    current_text = await page.locator(selector).inner_text()
                    if current_text != initial_text:
                        logger.info(f"Element updated: '{initial_text}' -> '{current_text}'")
                        return True
                except Exception:
                    pass
                
                await asyncio.sleep(0.3)
            
            return False
        
        except Exception as e:
            logger.error(f"Error waiting for element update: {e}")
            return False
    
    async def wait_for_custom_condition(
        self,
        condition_func: Callable[[], Any],
        expected_result: Any = True,
        timeout_ms: Optional[int] = None,
        poll_interval_ms: int = 500,
    ) -> bool:
        """
        Wait for a custom condition to be true.
        
        Args:
            condition_func: Async function that returns condition result
            expected_result: The result we're waiting for (default: True)
            timeout_ms: Timeout in milliseconds
            poll_interval_ms: How often to check condition
        
        Returns:
            True if condition met within timeout
        """
        timeout = timeout_ms or self.config.custom_condition_timeout_ms
        start_time = time.time()
        
        try:
            while time.time() - start_time < timeout / 1000:
                try:
                    result = await condition_func()
                    if result == expected_result:
                        logger.info("Custom condition satisfied")
                        return True
                except Exception as e:
                    logger.debug(f"Condition check failed: {e}")
                
                await asyncio.sleep(poll_interval_ms / 1000)
            
            logger.warning(f"Custom condition timeout after {timeout}ms")
            return False
        
        except Exception as e:
            logger.error(f"Error in custom condition: {e}")
            return False
    
    async def wait_for_images_loaded(
        self,
        page: Page,
        timeout_ms: Optional[int] = None,
    ) -> int:
        """
        Wait for images to load.
        
        Returns:
            Number of images loaded
        """
        timeout = timeout_ms or self.config.load_state_timeout_ms
        
        try:
            images_loaded = await page.evaluate(
                f"""
                async () => {{
                    const timeout = {timeout};
                    const start = Date.now();
                    let count = 0;
                    
                    const images = document.querySelectorAll('img');
                    const promises = Array.from(images).map(img => 
                        new Promise(resolve => {{
                            if (img.complete) {{
                                resolve();
                            }} else {{
                                img.addEventListener('load', resolve);
                                img.addEventListener('error', resolve);
                                setTimeout(resolve, timeout);
                            }}
                        }})
                    );
                    
                    await Promise.all(promises);
                    return images.length;
                }}
                """
            )
            logger.info(f"Waited for {images_loaded} images to load")
            return images_loaded
        
        except Exception as e:
            logger.error(f"Error waiting for images: {e}")
            return 0
    
    async def smart_scroll_to_load(
        self,
        page: Page,
        max_scrolls: int = 5,
        check_interval_ms: int = 500,
        timeout_ms: Optional[int] = None,
    ) -> int:
        """
        Smart scrolling that waits for content to appear rather than fixed delays.
        
        Returns:
            Total height scrolled to
        """
        timeout = timeout_ms or (self.config.idle_timeout_ms * max_scrolls)
        start_time = time.time()
        current_height = 0
        
        try:
            for scroll_num in range(max_scrolls):
                # Check timeout
                if time.time() - start_time > timeout / 1000:
                    logger.warning(f"Smart scroll timeout after {scroll_num} scrolls")
                    break
                
                # Get initial height
                before_height = await page.evaluate("document.documentElement.scrollHeight")
                
                # Scroll
                await page.evaluate("window.scrollBy(0, 800)")
                
                # Wait for new content
                height_changed = await self.wait_for_scrollable_content(
                    page,
                    before_height,
                    timeout_ms=check_interval_ms,
                )
                
                current_height = height_changed or before_height
                
                if not height_changed:
                    logger.info(f"No new content after scroll {scroll_num + 1}, stopping")
                    break
            
            return current_height
        
        except Exception as e:
            logger.error(f"Error in smart scroll: {e}")
            return current_height


# Global smart wait engine
_smart_wait = SmartWaitEngine()


def get_smart_wait_engine() -> SmartWaitEngine:
    """Get global smart wait engine."""
    return _smart_wait
