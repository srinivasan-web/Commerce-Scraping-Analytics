from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from backend.app.schemas import DashboardSummary, Product


def safe_score(value: float, maximum: float) -> float:
    if maximum <= 0:
        return 0
    return round(min((value / maximum) * 100, 100), 2)


def enrich_product_scores(products: list[Product]) -> list[Product]:
    max_revenue = max((item.revenue for item in products), default=1)
    max_units = max((item.units_sold for item in products), default=1)
    max_reviews = max((item.reviews for item in products), default=1)
    enriched: list[Product] = []
    for product in products:
        performance = ((product.rating or 0) * max(product.reviews, 1) * max(product.units_sold, 1)) / max(product.price, 1)
        product.scores = {
            "revenue_score": safe_score(product.revenue, max_revenue),
            "demand_score": safe_score(product.units_sold, max_units),
            "bestseller_score": round((safe_score(product.reviews, max_reviews) + safe_score(product.rating, 5)) / 2, 2),
            "performance_score": round(min(performance / 250, 100), 2),
            "sales_velocity": round(product.units_sold / 30, 2),
            "rating_quality_score": safe_score(product.rating, 5),
            "trend_score": round((safe_score(product.units_sold, max_units) * 0.7) + (safe_score(product.reviews, max_reviews) * 0.3), 2),
            "price_competitiveness": round(100 - min((product.price / max((product.original_price or product.price or 1), 1)) * 100, 100), 2),
            "offer_strength": min(round(product.discount + (10 if product.coupon_available else 0) + (8 if product.prime_available else 0), 2), 100),
        }
        product.monthly_units_sold = product.units_sold
        product.estimated_monthly_revenue = product.revenue
        product.sales_velocity = product.scores["sales_velocity"]
        product.demand_score = product.scores["demand_score"]
        product.discount_amount = max(round((product.original_price or 0) - product.price, 2), 0)
        product.final_effective_price = max(round(product.price - product.coupon_amount, 2), 0)
        product.in_stock = "out of stock" not in (product.availability or "").lower() and "unavailable" not in (product.availability or "").lower()
        product.out_of_stock = not product.in_stock
        enriched.append(product)
    return enriched


def build_dashboard_summary(products: list[Product], active_jobs: int, total_jobs: int, completed_jobs: int) -> DashboardSummary:
    revenue = sum(item.revenue for item in products)
    visible_bought_count = sum(item.visible_bought_count for item in products)
    estimated_units = sum(item.units_sold for item in products if item.units_sold_estimated)
    ratings = [item.rating for item in products if item.rating]
    categories: dict[str, float] = defaultdict(float)
    for product in products:
        categories[product.category or "General"] += product.revenue
    top_category = max(categories.items(), key=lambda item: item[1])[0] if categories else "None"
    return DashboardSummary(
        total_products=len({item.parent_asin or item.id for item in products}),
        total_variants=len(products),
        total_revenue=round(revenue, 2),
        average_rating=round(sum(ratings) / len(ratings), 2) if ratings else 0,
        units_sold=sum(item.units_sold for item in products),
        visible_bought_count=visible_bought_count,
        estimated_units=estimated_units,
        top_category=top_category,
        active_jobs=active_jobs,
        success_rate=round((completed_jobs / total_jobs) * 100, 2) if total_jobs else 100,
    )


def revenue_by_category(products: list[Product]) -> list[dict[str, float | str]]:
    buckets: dict[str, float] = defaultdict(float)
    for product in products:
        buckets[product.category or "General"] += product.revenue
    return [{"name": key, "revenue": round(value, 2)} for key, value in sorted(buckets.items())]


def variant_distribution(products: list[Product]) -> list[dict[str, float | str]]:
    buckets: dict[str, float] = defaultdict(float)
    for product in products:
        buckets[product.variant or product.color or product.size or "Default"] += product.revenue
    return [{"name": key[:28], "value": round(value, 2)} for key, value in sorted(buckets.items(), key=lambda item: item[1], reverse=True)[:12]]


def revenue_trend(products: list[Product]) -> list[dict[str, float | str]]:
    today = datetime.utcnow().date()
    base = {today - timedelta(days=offset): 0.0 for offset in range(6, -1, -1)}
    for product in products:
        base[product.scraped_at.date()] = base.get(product.scraped_at.date(), 0) + product.revenue
    return [{"date": day.strftime("%b %d"), "revenue": round(value, 2)} for day, value in base.items()]


def ai_insights(products: list[Product]) -> list[dict[str, str | float]]:
    if not products:
        return [{"title": "No live data yet", "detail": "Start a scrape to generate product, demand, revenue, and offer intelligence.", "score": 0}]
    by_revenue = max(products, key=lambda item: item.revenue)
    by_demand = max(products, key=lambda item: item.units_sold)
    by_discount = max(products, key=lambda item: item.discount)
    by_conversion = max(products, key=lambda item: item.scores.get("performance_score", 0))
    return [
        {"title": "Top revenue product", "detail": f"{by_revenue.name} leads with {by_revenue.revenue:,.2f} estimated revenue.", "score": round(by_revenue.scores.get("revenue_score", 0), 2)},
        {"title": "Highest demand variant", "detail": f"{by_demand.variant or by_demand.name} shows {by_demand.units_sold:,} monthly units.", "score": round(by_demand.scores.get("demand_score", 0), 2)},
        {"title": "Strongest discount", "detail": f"{by_discount.name} has a {by_discount.discount:.1f}% visible discount.", "score": round(by_discount.discount, 2)},
        {"title": "Best conversion potential", "detail": f"{by_conversion.name} combines rating, reviews, units, and price most efficiently.", "score": round(by_conversion.scores.get("performance_score", 0), 2)},
    ]


def revenue_forecast(products: list[Product]) -> list[dict[str, float | str]]:
    total = sum(item.revenue for item in products)
    growth = 0.06
    return [
        {"period": f"Month {index}", "forecast": round(total * ((1 + growth) ** index), 2), "growth_rate": round(growth * 100, 2)}
        for index in range(1, 7)
    ]
