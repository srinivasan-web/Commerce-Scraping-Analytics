from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class Website(str, Enum):
    amazon = "amazon"
    flipkart = "flipkart"
    myntra = "myntra"
    ajio = "ajio"
    ebay = "ebay"
    alibaba = "alibaba"
    walmart = "walmart"
    auto = "auto"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    stopped = "stopped"


class ScrapeOptions(BaseModel):
    """Options for scraping with slider-based controls."""
    use_proxy: bool = False
    headless: bool = True
    max_products: int = Field(default=24, ge=1, le=100, description="Max products to scrape (1-100 slider)")
    variant_depth: int = Field(default=2, ge=0, le=5, description="Product variant depth (0-5 slider)")
    export_format: str = "xlsx"
    include_reviews: bool = True
    include_variants: bool = True
    external_service: bool = False
    high_priority: bool = False  # For async job queue priority
    
    # New slider controls for dashboard
    timeout_seconds: int = Field(default=30, ge=10, le=120, description="Timeout for each page load (10-120 slider)")
    concurrent_products: int = Field(default=5, ge=1, le=10, description="Concurrent product fetches (1-10 slider)")
    max_pages: int = Field(default=1, ge=1, le=10, description="Max pages to scrape (1-10 slider)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "max_products": 50,
                "variant_depth": 3,
                "timeout_seconds": 60,
                "concurrent_products": 5,
                "max_pages": 2,
                "include_reviews": True,
                "include_variants": True,
                "high_priority": False,
            }
        }


class ScrapeRequest(BaseModel):
    """Request to start a scraping job with slider-based parameters."""
    url: HttpUrl
    website: Website = Website.auto
    options: ScrapeOptions = Field(default_factory=ScrapeOptions)
    
    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://www.amazon.in/gp/bestsellers/sports/",
                "website": "amazon",
                "options": {
                    "max_products": 50,
                    "variant_depth": 3,
                    "timeout_seconds": 60,
                    "concurrent_products": 5,
                }
            }
        }


class Product(BaseModel):
    id: str
    job_id: str
    product_rank: str = ""
    rank_number: int = 0
    name: str
    brand_name: str = ""
    website: Website
    category: str = "General"
    subcategory: str = ""
    parent_asin: str = ""
    variant_asin: str = ""
    variant: str = "Default"
    variant_name: str = "Default"
    variant_type: str = "Default"
    color: str = ""
    size: str = ""
    weight: str = ""
    model: str = ""
    package: str = ""
    flavor: str = ""
    storage: str = ""
    combo: str = ""
    sku: str = ""
    price: float = 0
    original_price: float = 0
    discount: float = 0
    discount_amount: float = 0
    coupon_amount: float = 0
    final_effective_price: float = 0
    rating: float = 0
    reviews: int = 0
    positive_review_percent: float = 0
    negative_review_percent: float = 0
    review_keywords: list[str] = Field(default_factory=list)
    units_sold: int = 0
    monthly_units_sold: int = 0
    revenue: float = 0
    estimated_monthly_revenue: float = 0
    sales_velocity: float = 0
    demand_score: float = 0
    offers: str = ""
    bank_offers: str = ""
    emi_offers: str = ""
    cashback_offers: str = ""
    coupon_offers: str = ""
    partner_offers: str = ""
    exchange_offers: str = ""
    delivery: str = ""
    fast_delivery: bool = False
    delivery_days: str = ""
    installation_available: bool = False
    warranty: str = ""
    availability: str = ""
    bought_count_text: str = ""
    price_text: str = ""
    original_price_text: str = ""
    discount_text: str = ""
    rating_text: str = ""
    reviews_text: str = ""
    prime_available: bool = False
    free_delivery: bool = False
    in_stock: bool = True
    out_of_stock: bool = False
    limited_stock: bool = False
    limited_time_deal: bool = False
    coupon_available: bool = False
    sponsored_status: bool = False
    bestseller_badge: bool = False
    amazon_choice_badge: bool = False
    raw_card_text: str = ""
    parent_product_revenue: float = 0
    visible_bought_count: int = 0
    units_sold_estimated: bool = False
    bought_count_source: str = ""
    image_url: str = ""
    variant_images: list[str] = Field(default_factory=list)
    gallery_images: list[str] = Field(default_factory=list)
    video_urls: list[str] = Field(default_factory=list)
    product_url: str = ""
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    scores: dict[str, float] = Field(default_factory=dict)

    @property
    def export_payload(self) -> dict[str, Any]:
        return {
            "Rank": self.rank_number or self.product_rank,
            "ASIN": self.parent_asin,
            "Overall Bought Count": self.visible_bought_count,
            "Product Price": self.price,
            "Total Revenue": self.parent_product_revenue or self.revenue,
            "Product Name": self.name,
            "Brand Name": self.brand_name,
            "Number of Reviews": self.reviews,
            "Rating": self.rating,
            "Product Rank": self.product_rank,
            "Rank Number": self.rank_number,
            "Product Price Text": self.price_text,
            "Original Price": self.original_price_text,
            "Original Price Value": self.original_price,
            "Discount Percentage": self.discount,
            "Discount Amount": self.discount_amount,
            "Coupon Amount": self.coupon_amount,
            "Final Effective Price": self.final_effective_price or self.price,
            "Discount Text": self.discount_text,
            "Product Rating": self.rating_text,
            "Product Rating Value": self.rating,
            "Number of Reviews Text": self.reviews_text,
            "Reviews Count": self.reviews,
            "Visible Bought Count": self.visible_bought_count,
            "Bought Count Text": self.bought_count_text,
            "Bought Count Source": self.bought_count_source,
            "Units Estimated": self.units_sold_estimated,
            "Monthly Units Used": self.units_sold,
            "Sales Velocity": self.sales_velocity,
            "Demand Score": self.demand_score or self.scores.get("demand_score", 0),
            "Bought x Price Revenue": self.revenue,
            "Estimated Monthly Revenue": self.revenue,
            "Product Total Revenue": self.parent_product_revenue or self.revenue,
            "Product URL": self.product_url,
            "Availability": self.availability,
            "Category": self.category,
            "Prime Available": self.prime_available,
            "Free Delivery": self.free_delivery,
            "Fast Delivery": self.fast_delivery,
            "Delivery Days": self.delivery_days,
            "Installation Available": self.installation_available,
            "Limited Time Deal": self.limited_time_deal,
            "Coupon Available": self.coupon_available,
            "Sponsored Status": self.sponsored_status,
            "Bestseller Badge": self.bestseller_badge,
            "Raw Card Text": self.raw_card_text,
            "Timestamp": self.scraped_at.isoformat(),
        }


class VariantAnalytics(BaseModel):
    variant_name: str
    color: str = ""
    size: str = ""
    package: str = ""
    capacity: str = ""
    units_sold: int
    variant_revenue: float
    demand_score: float
    conversion_score: float


class Job(BaseModel):
    id: str
    status: JobStatus
    url: str
    website: Website
    progress: int = 0
    current_product: str = ""
    completed_products: int = 0
    remaining_products: int = 0
    revenue: float = 0
    units_sold: int = 0
    visible_bought_count: int = 0
    estimated_units: int = 0
    captcha_alert: bool = False
    external_job_id: str = ""
    external_status_url: str = ""
    organization_id: str = "demo-org"
    logs: list[str] = Field(default_factory=list)
    products: list[Product] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None  # When job started running
    completed_at: datetime | None = None  # When job completed


class DashboardSummary(BaseModel):
    total_products: int
    total_variants: int
    total_revenue: float
    average_rating: float
    units_sold: int
    visible_bought_count: int
    estimated_units: int
    top_category: str
    active_jobs: int
    success_rate: float


class AnalyticsResponse(BaseModel):
    summary: DashboardSummary
    revenue_by_category: list[dict[str, Any]]
    revenue_trend: list[dict[str, Any]]
    variant_distribution: list[dict[str, Any]]
    top_products: list[Product]
    ai_insights: list[dict[str, Any]] = Field(default_factory=list)
    revenue_forecast: list[dict[str, Any]] = Field(default_factory=list)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)
    organization: str = "Default Organization"


class AuthSession(BaseModel):
    access_token: str
    organization_id: str
    organization_name: str
    user_email: str
    api_key: str


class ApiKey(BaseModel):
    id: str
    organization_id: str
    name: str
    key_preview: str
    key: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = True


class ApiKeyCreate(BaseModel):
    name: str = Field(default="Dashboard Key", min_length=1, max_length=80)


# ======================== NEW MODELS FOR REAL-TIME DASHBOARD ========================

class ProgressUpdate(BaseModel):
    """Real-time progress update for WebSocket."""
    job_id: str
    step: int
    stage: str
    message: str
    progress: int  # 0-100
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    products_found: int = 0
    current_product: str = ""


class JobDetailResponse(BaseModel):
    """Comprehensive job status with detailed metrics."""
    job_id: str
    status: JobStatus
    progress: int  # 0-100
    url: str
    website: Website
    total_products: int
    products_found: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    estimated_completion: datetime | None = None
    duration_seconds: int = 0
    current_step: int  # 1-5
    stage: str  # initializing, loading, extracting, enriching, finalizing, complete
    message: str  # User-friendly message
    speed: float = 0.0  # products per second
    avg_time_per_product: float = 0.0  # seconds
    success_rate: float = 100.0  # percentage


class SystemHealthResponse(BaseModel):
    """System health metrics for dashboard monitoring."""
    status: str
    timestamp: datetime
    version: str
    components: dict[str, dict[str, Any]] = Field(default_factory=dict)
    performance: dict[str, Any] = Field(default_factory=dict)
    queue_status: dict[str, int] = Field(default_factory=dict)
