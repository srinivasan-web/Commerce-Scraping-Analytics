from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from app.schemas import Job, JobStatus, Product, Website


class JobStore:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    async def create_job(self, job: Job) -> Job:
        async with self._lock:
            self.jobs[job.id] = job
        await self.publish(job.id, {"type": "job.created", "job": job.model_dump(mode="json")})
        return job

    async def get_job(self, job_id: str) -> Job | None:
        async with self._lock:
            return self.jobs.get(job_id)

    async def list_jobs(self) -> list[Job]:
        async with self._lock:
            return sorted(self.jobs.values(), key=lambda item: item.created_at, reverse=True)

    async def products(self, job_id: str | None = None, organization_id: str | None = None) -> list[Product]:
        async with self._lock:
            jobs = [self.jobs[job_id]] if job_id and job_id in self.jobs else self.jobs.values()
            rows: list[Product] = []
            for job in jobs:
                if organization_id and job.organization_id != organization_id:
                    continue
                rows.extend(job.products)
            return rows

    async def update_job(self, job_id: str, **updates: Any) -> Job:
        async with self._lock:
            job = self.jobs[job_id]
            for key, value in updates.items():
                setattr(job, key, value)
            job.updated_at = datetime.utcnow()
            self.jobs[job_id] = job
        await self.publish(job_id, {"type": "job.updated", "job": job.model_dump(mode="json")})
        return job

    async def append_log(self, job_id: str, message: str) -> None:
        job = await self.get_job(job_id)
        if not job:
            return
        logs = [*job.logs, f"{datetime.utcnow().strftime('%H:%M:%S')} {message}"][-300:]
        await self.update_job(job_id, logs=logs)
        await self.publish(job_id, {"type": "log", "message": message})

    async def add_product(self, job_id: str, product: Product) -> None:
        job = await self.get_job(job_id)
        if not job:
            return
        products = [*job.products, product]
        await self.update_job(
            job_id,
            products=products,
            completed_products=len(products),
            revenue=sum(item.revenue for item in products),
            units_sold=sum(item.units_sold for item in products),
            visible_bought_count=sum(item.visible_bought_count for item in products),
            estimated_units=sum(item.units_sold for item in products if item.units_sold_estimated),
        )

    async def set_status(self, job_id: str, status: JobStatus) -> None:
        await self.update_job(job_id, status=status)

    async def subscribe(self, job_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.setdefault(job_id, set()).add(queue)
        job = await self.get_job(job_id)
        if job:
            await queue.put({"type": "snapshot", "job": job.model_dump(mode="json")})
        return queue

    async def unsubscribe(self, job_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subscribers = self._subscribers.get(job_id)
        if subscribers:
            subscribers.discard(queue)

    async def publish(self, job_id: str, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(job_id, set())):
            await queue.put(event)


store = JobStore()


async def seed_store() -> None:
    if await store.list_jobs():
        return
    job = Job(
        id="demo-job",
        status=JobStatus.completed,
        url="https://www.amazon.in/gp/bestsellers",
        website=Website.amazon,
        progress=100,
        current_product="Completed demo scrape",
    )
    await store.create_job(job)
    samples = [
        ("Adjustable Dumbbell Set", "Fitness", 4999, 4.5, 1832, 780, "Black", "20kg"),
        ("Yoga Mat Pro Grip", "Fitness", 899, 4.3, 8124, 2500, "Purple", "6mm"),
        ("Running Shoes AirFlex", "Footwear", 2499, 4.1, 3422, 930, "Blue", "UK 9"),
        ("Copper Water Bottle", "Kitchen", 699, 4.4, 6210, 4200, "Copper", "1L"),
        ("Wireless Neckband", "Electronics", 1299, 4.0, 2102, 1400, "Black", "Standard"),
        ("Resistance Band Kit", "Fitness", 649, 4.2, 1880, 1700, "Multi", "11 pcs"),
    ]
    for index, (name, category, price, rating, reviews, units, color, size) in enumerate(samples, start=1):
        product = Product(
            id=f"demo-{index}",
            job_id=job.id,
            name=name,
            website=Website.amazon,
            category=category,
            parent_asin=f"DEMO{index:06d}",
            variant_asin=f"DEMO{index:06d}V",
            variant=f"{color} / {size}",
            color=color,
            size=size,
            price=price,
            original_price=round(price * 1.25, 2),
            discount=20,
            rating=rating,
            reviews=reviews,
            units_sold=units,
            visible_bought_count=units,
            bought_count_text=f"{units}+ bought in past month",
            bought_count_source="visible",
            revenue=price * units,
            offers="Bank offer, coupon eligible",
            delivery="2-4 days",
            warranty="Standard policy",
            product_url="https://www.amazon.in/",
            scores={},
        )
        await store.add_product(job.id, product)
    products = await store.products(job.id)
    await store.update_job(
        job.id,
        completed_products=len(products),
        remaining_products=0,
        revenue=sum(p.revenue for p in products),
        units_sold=sum(p.units_sold for p in products),
        visible_bought_count=sum(p.visible_bought_count for p in products),
        estimated_units=sum(p.units_sold for p in products if p.units_sold_estimated),
    )
