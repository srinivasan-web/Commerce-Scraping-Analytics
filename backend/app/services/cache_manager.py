"""
Intelligent caching layer for avoiding re-scraping duplicate products.
Features:
- In-memory cache with LRU eviction
- Hash-based duplicate detection
- Configurable TTL (Time-To-Live)
- Thread-safe operations
"""

from __future__ import annotations

import hashlib
import json
import time
import asyncio
from collections import OrderedDict
from typing import Optional, Any
from datetime import datetime, timedelta

from app.schemas import Product


class CacheEntry:
    """Single cache entry with TTL and metadata."""
    
    def __init__(self, data: Any, ttl_seconds: int = 3600):
        self.data = data
        self.created_at = time.time()
        self.accessed_at = self.created_at
        self.ttl_seconds = ttl_seconds
        self.access_count = 1
    
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return (time.time() - self.created_at) > self.ttl_seconds
    
    def access(self) -> Any:
        """Mark as accessed and return data."""
        self.accessed_at = time.time()
        self.access_count += 1
        return self.data


class InMemoryCache:
    """Fast in-memory cache with LRU eviction policy."""
    
    def __init__(self, max_items: int = 10000, default_ttl: int = 3600):
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.max_items = max_items
        self.default_ttl = default_ttl
        self.lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache if exists and not expired."""
        async with self.lock:
            if key not in self.cache:
                self.misses += 1
                return None
            
            entry = self.cache[key]
            if entry.is_expired():
                del self.cache[key]
                self.misses += 1
                return None
            
            # Move to end (most recently used)
            self.cache.move_to_end(key)
            self.hits += 1
            return entry.access()
    
    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Set value in cache."""
        async with self.lock:
            ttl = ttl_seconds or self.default_ttl
            entry = CacheEntry(value, ttl)
            
            if key in self.cache:
                del self.cache[key]
            
            self.cache[key] = entry
            
            # Evict oldest if over limit
            if len(self.cache) > self.max_items:
                self.cache.popitem(last=False)
    
    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        async with self.lock:
            self.cache.pop(key, None)
    
    async def clear(self) -> None:
        """Clear entire cache."""
        async with self.lock:
            self.cache.clear()
    
    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        async with self.lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
            return {
                "total_items": len(self.cache),
                "max_items": self.max_items,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(hit_rate, 2),
                "total_requests": total_requests,
            }


class ContentHash:
    """Generate consistent hashes for duplicate detection."""
    
    @staticmethod
    def product_hash(product: Product) -> str:
        """Generate hash from product's key attributes."""
        key_data = {
            "name": product.name[:50].lower().strip(),
            "brand": product.brand_name.lower().strip() if product.brand_name else "",
            "price": product.price,
            "asin": product.parent_asin[:8] if product.parent_asin else "",
        }
        json_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()
    
    @staticmethod
    def url_hash(url: str) -> str:
        """Generate hash from URL."""
        return hashlib.sha256(url.lower().strip().encode()).hexdigest()
    
    @staticmethod
    def card_hash(card: dict) -> str:
        """Generate hash from extracted card data."""
        key_fields = {
            "name": str(card.get("name", ""))[:50].lower(),
            "price": card.get("price", ""),
            "id": str(card.get("id", ""))[:10].lower(),
        }
        json_str = json.dumps(key_fields, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()


class DuplicateDetector:
    """Detect duplicate products using multiple strategies."""
    
    def __init__(self):
        self.product_hashes: set[str] = set()
        self.url_cache: dict[str, list[str]] = {}  # URL -> list of product hashes
        self.lock = asyncio.Lock()
    
    async def is_duplicate_product(self, product: Product) -> bool:
        """Check if product is duplicate based on key attributes."""
        async with self.lock:
            product_hash = ContentHash.product_hash(product)
            is_dup = product_hash in self.product_hashes
            if not is_dup:
                self.product_hashes.add(product_hash)
            return is_dup
    
    async def register_url_products(self, url: str, products: list[Product]) -> None:
        """Register all products from a URL."""
        async with self.lock:
            url_hash = ContentHash.url_hash(url)
            hashes = [ContentHash.product_hash(p) for p in products]
            self.url_cache[url_hash] = hashes
            self.product_hashes.update(hashes)
    
    async def get_new_products(self, url: str, products: list[Product]) -> list[Product]:
        """Filter products, returning only new ones."""
        async with self.lock:
            new_products = []
            for product in products:
                product_hash = ContentHash.product_hash(product)
                if product_hash not in self.product_hashes:
                    new_products.append(product)
                    self.product_hashes.add(product_hash)
            return new_products
    
    async def clear(self) -> None:
        """Clear duplicate detection data."""
        async with self.lock:
            self.product_hashes.clear()
            self.url_cache.clear()


# Global cache instances
_cache = InMemoryCache(max_items=10000, default_ttl=3600)  # 1 hour TTL
_duplicate_detector = DuplicateDetector()


def get_cache() -> InMemoryCache:
    """Get global cache instance."""
    return _cache


def get_duplicate_detector() -> DuplicateDetector:
    """Get global duplicate detector instance."""
    return _duplicate_detector


async def cache_product_list(url: str, products: list[Product], ttl_seconds: int = 3600) -> None:
    """Cache a list of products by URL."""
    cache = get_cache()
    url_hash = ContentHash.url_hash(url)
    await cache.set(url_hash, products, ttl_seconds)


async def get_cached_products(url: str) -> Optional[list[Product]]:
    """Get cached products for a URL."""
    cache = get_cache()
    url_hash = ContentHash.url_hash(url)
    return await cache.get(url_hash)


async def invalidate_url_cache(url: str) -> None:
    """Invalidate cache for a specific URL."""
    cache = get_cache()
    url_hash = ContentHash.url_hash(url)
    await cache.delete(url_hash)
