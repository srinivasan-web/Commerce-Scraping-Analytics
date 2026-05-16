"""
Shared configuration notes for the terminal scraper.

The active runtime reads these same environment variable names directly in
main.py so the scraper remains a single-command backend. Keep this file as the
operator-facing config map for deployments, scheduled jobs, and future package
splits.
"""

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class ScraperConfig:
    target_url: str = getenv(
        "TARGET_URL",
        "https://www.amazon.in/gp/bestsellers/sports/3404687031/ref=pd_zg_hrsr_sports",
    )
    amazon_base_url: str = getenv("AMAZON_BASE_URL", "https://www.amazon.in")
    max_parent_products: int = int(getenv("MAX_PARENT_PRODUCTS", "50"))
    max_bestseller_pages: int = int(getenv("MAX_BESTSELLER_PAGES", "2"))
    max_variants_per_product: int = int(getenv("MAX_VARIANTS_PER_PRODUCT", "30"))
    detail_page_concurrency: int = int(getenv("DETAIL_PAGE_CONCURRENCY", "4"))
    scrape_variants: bool = getenv("SCRAPE_VARIANTS", "true").lower() == "true"
    block_static_assets: bool = getenv("BLOCK_STATIC_ASSETS", "true").lower() == "true"
    slow_mo_ms: int = int(getenv("SLOW_MO_MS", "80"))
    detail_load_delay: float = float(getenv("DETAIL_LOAD_DELAY", "0.7"))
    request_timeout_ms: int = int(getenv("REQUEST_TIMEOUT_MS", "60000"))
    playwright_proxy: str = getenv("PLAYWRIGHT_PROXY", "")
