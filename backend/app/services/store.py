from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from typing import Any

try:
    import asyncpg
except ModuleNotFoundError:  # Local fallback when backend requirements are not installed yet.
    asyncpg = None  # type: ignore[assignment]

from app.schemas import Job, JobStatus, Product, Website


def _database_url() -> str:
    return os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or ""


def _json_payload(model: Job | Product | dict[str, Any] | list[Any]) -> str:
    if isinstance(model, (Job, Product)):
        return json.dumps(model.model_dump(mode="json"))
    return json.dumps(model)


def _parse_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value


class JobStore:
    """Persistent job/product store with an in-memory fallback for local setup."""

    JOB_COLUMNS = {
        "status",
        "url",
        "website",
        "progress",
        "current_product",
        "completed_products",
        "remaining_products",
        "revenue",
        "units_sold",
        "visible_bought_count",
        "estimated_units",
        "captcha_alert",
        "external_job_id",
        "external_status_url",
        "organization_id",
        "logs",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
    }

    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._pool: Any | None = None
        self._initialized = False

    @property
    def persistent(self) -> bool:
        return self._pool is not None

    async def initialize(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        url = _database_url()
        if not url:
            return
        if asyncpg is None:
            raise RuntimeError("DATABASE_URL is set, but asyncpg is not installed. Run pip install -r backend/requirements.txt.")
        self._pool = await asyncpg.create_pool(
            dsn=url,
            min_size=1,
            max_size=max(1, min(int(os.getenv("DATABASE_POOL_SIZE", "2")), 5)),
            command_timeout=30,
        )
        await self._migrate()

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
        self._pool = None
        self._initialized = False

    async def _migrate(self) -> None:
        if not self._pool:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_jobs (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL DEFAULT 'demo-org',
                    url TEXT NOT NULL,
                    website TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    progress INTEGER NOT NULL DEFAULT 0,
                    current_product TEXT NOT NULL DEFAULT '',
                    completed_products INTEGER NOT NULL DEFAULT 0,
                    remaining_products INTEGER NOT NULL DEFAULT 0,
                    revenue DOUBLE PRECISION NOT NULL DEFAULT 0,
                    units_sold INTEGER NOT NULL DEFAULT 0,
                    visible_bought_count INTEGER NOT NULL DEFAULT 0,
                    estimated_units INTEGER NOT NULL DEFAULT 0,
                    captcha_alert BOOLEAN NOT NULL DEFAULT FALSE,
                    external_job_id TEXT NOT NULL DEFAULT '',
                    external_status_url TEXT NOT NULL DEFAULT '',
                    logs JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ
                );

                CREATE TABLE IF NOT EXISTS app_products (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES app_jobs(id) ON DELETE CASCADE,
                    organization_id TEXT NOT NULL DEFAULT 'demo-org',
                    payload JSONB NOT NULL,
                    revenue DOUBLE PRECISION NOT NULL DEFAULT 0,
                    units_sold INTEGER NOT NULL DEFAULT 0,
                    visible_bought_count INTEGER NOT NULL DEFAULT 0,
                    scraped_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE INDEX IF NOT EXISTS idx_app_jobs_org_created
                    ON app_jobs (organization_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_app_products_job
                    ON app_products (job_id);
                CREATE INDEX IF NOT EXISTS idx_app_products_org
                    ON app_products (organization_id);
                """
            )

    def _job_from_record(self, record: Any) -> Job:
        data = dict(record)
        data["logs"] = _parse_json(data.get("logs"), [])
        data["products"] = []
        return Job.model_validate(data)

    async def _publish_job(self, job_id: str, event_type: str = "job.updated") -> None:
        job = await self.get_job(job_id)
        if job:
            await self.publish(job_id, {"type": event_type, "job": job.model_dump(mode="json")})

    async def create_job(self, job: Job) -> Job:
        await self.initialize()
        if self._pool:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO app_jobs (
                        id, organization_id, url, website, status, progress, current_product,
                        completed_products, remaining_products, revenue, units_sold,
                        visible_bought_count, estimated_units, captcha_alert, external_job_id,
                        external_status_url, logs, created_at, updated_at, started_at, completed_at
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                        $12, $13, $14, $15, $16, $17::jsonb, $18, $19, $20, $21
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        organization_id = EXCLUDED.organization_id,
                        url = EXCLUDED.url,
                        website = EXCLUDED.website,
                        status = EXCLUDED.status,
                        updated_at = now()
                    """,
                    job.id,
                    job.organization_id,
                    job.url,
                    job.website.value,
                    job.status.value,
                    job.progress,
                    job.current_product,
                    job.completed_products,
                    job.remaining_products,
                    job.revenue,
                    job.units_sold,
                    job.visible_bought_count,
                    job.estimated_units,
                    job.captcha_alert,
                    job.external_job_id,
                    job.external_status_url,
                    _json_payload(job.logs),
                    job.created_at,
                    job.updated_at,
                    job.started_at,
                    job.completed_at,
                )
        else:
            async with self._lock:
                self.jobs[job.id] = job
        await self.publish(job.id, {"type": "job.created", "job": job.model_dump(mode="json")})
        return job

    async def get_job(self, job_id: str) -> Job | None:
        await self.initialize()
        if self._pool:
            async with self._pool.acquire() as conn:
                record = await conn.fetchrow("SELECT * FROM app_jobs WHERE id = $1", job_id)
            return self._job_from_record(record) if record else None
        async with self._lock:
            job = self.jobs.get(job_id)
            return job.model_copy(deep=True) if job else None

    async def list_jobs(self) -> list[Job]:
        await self.initialize()
        if self._pool:
            async with self._pool.acquire() as conn:
                records = await conn.fetch("SELECT * FROM app_jobs ORDER BY created_at DESC LIMIT 250")
            return [self._job_from_record(record) for record in records]
        async with self._lock:
            return sorted((job.model_copy(deep=True) for job in self.jobs.values()), key=lambda item: item.created_at, reverse=True)

    async def storage_status(self) -> dict[str, Any]:
        await self.initialize()
        if self._pool:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM app_jobs) AS jobs,
                        (SELECT COUNT(*) FROM app_products) AS products
                    """
                )
            return {"storage": "postgres", "persistent": True, "jobs": int(row["jobs"]), "products": int(row["products"])}
        async with self._lock:
            return {
                "storage": "memory",
                "persistent": False,
                "jobs": len(self.jobs),
                "products": sum(len(job.products) for job in self.jobs.values()),
            }

    async def products(self, job_id: str | None = None, organization_id: str | None = None) -> list[Product]:
        await self.initialize()
        if self._pool:
            where: list[str] = []
            args: list[Any] = []
            if job_id:
                args.append(job_id)
                where.append(f"job_id = ${len(args)}")
            if organization_id:
                args.append(organization_id)
                where.append(f"organization_id = ${len(args)}")
            query = "SELECT payload FROM app_products"
            if where:
                query += " WHERE " + " AND ".join(where)
            query += " ORDER BY scraped_at DESC, id DESC"
            async with self._pool.acquire() as conn:
                records = await conn.fetch(query, *args)
            return [Product.model_validate(_parse_json(record["payload"], {})) for record in records]
        async with self._lock:
            jobs = [self.jobs[job_id]] if job_id and job_id in self.jobs else self.jobs.values()
            rows: list[Product] = []
            for job in jobs:
                if organization_id and job.organization_id != organization_id:
                    continue
                rows.extend(product.model_copy(deep=True) for product in job.products)
            return rows

    async def update_job(self, job_id: str, **updates: Any) -> Job:
        await self.initialize()
        updates = dict(updates)
        products_update = updates.pop("products", None)
        now = datetime.utcnow()
        if "status" in updates:
            status = updates["status"]
            status_value = status.value if isinstance(status, JobStatus) else str(status)
            if status_value == JobStatus.running.value:
                updates.setdefault("started_at", now)
            if status_value in {JobStatus.completed.value, JobStatus.failed.value, JobStatus.stopped.value}:
                updates.setdefault("completed_at", now)
        updates["updated_at"] = now

        if self._pool:
            clean_updates = {key: value for key, value in updates.items() if key in self.JOB_COLUMNS}
            if products_update == []:
                async with self._pool.acquire() as conn:
                    await conn.execute("DELETE FROM app_products WHERE job_id = $1", job_id)
            if clean_updates:
                assignments: list[str] = []
                values: list[Any] = []
                for key, value in clean_updates.items():
                    if isinstance(value, (JobStatus, Website)):
                        value = value.value
                    if key == "logs":
                        value = _json_payload(value)
                        assignments.append(f"{key} = ${len(values) + 1}::jsonb")
                    else:
                        assignments.append(f"{key} = ${len(values) + 1}")
                    values.append(value)
                values.append(job_id)
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        f"UPDATE app_jobs SET {', '.join(assignments)} WHERE id = ${len(values)}",
                        *values,
                    )
            await self._publish_job(job_id)
            job = await self.get_job(job_id)
            if not job:
                raise KeyError(job_id)
            return job

        async with self._lock:
            job = self.jobs[job_id]
            for key, value in updates.items():
                if key in self.JOB_COLUMNS:
                    setattr(job, key, value)
            if products_update == []:
                job.products = []
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
        await self.add_products(job_id, [product])

    async def add_products(self, job_id: str, new_products: list[Product]) -> None:
        if not new_products:
            return
        await self.initialize()
        job = await self.get_job(job_id)
        if not job:
            return

        if self._pool:
            rows = [
                (
                    product.id,
                    job_id,
                    job.organization_id,
                    _json_payload(product),
                    product.revenue,
                    product.units_sold,
                    product.visible_bought_count,
                    product.scraped_at,
                )
                for product in new_products
            ]
            async with self._pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO app_products (
                        id, job_id, organization_id, payload, revenue, units_sold,
                        visible_bought_count, scraped_at
                    )
                    VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8)
                    ON CONFLICT (id) DO UPDATE SET
                        payload = EXCLUDED.payload,
                        revenue = EXCLUDED.revenue,
                        units_sold = EXCLUDED.units_sold,
                        visible_bought_count = EXCLUDED.visible_bought_count,
                        scraped_at = EXCLUDED.scraped_at
                    """,
                    rows,
                )
                summary = await conn.fetchrow(
                    """
                    SELECT
                        COUNT(*) AS completed_products,
                        COALESCE(SUM(revenue), 0) AS revenue,
                        COALESCE(SUM(units_sold), 0) AS units_sold,
                        COALESCE(SUM(visible_bought_count), 0) AS visible_bought_count,
                        COALESCE(
                            SUM(
                                CASE
                                    WHEN COALESCE((payload->>'units_sold_estimated')::boolean, false)
                                    THEN units_sold
                                    ELSE 0
                                END
                            ),
                            0
                        ) AS estimated_units
                    FROM app_products
                    WHERE job_id = $1
                    """,
                    job_id,
                )
            await self.update_job(
                job_id,
                completed_products=int(summary["completed_products"]),
                remaining_products=0,
                revenue=float(summary["revenue"]),
                units_sold=int(summary["units_sold"]),
                visible_bought_count=int(summary["visible_bought_count"]),
                estimated_units=int(summary["estimated_units"]),
            )
            return

        async with self._lock:
            current = self.jobs[job_id]
            products = [*current.products, *new_products]
            current.products = products
            current.completed_products = len(products)
            current.remaining_products = 0
            current.revenue = sum(item.revenue for item in products)
            current.units_sold = sum(item.units_sold for item in products)
            current.visible_bought_count = sum(item.visible_bought_count for item in products)
            current.estimated_units = sum(item.units_sold for item in products if item.units_sold_estimated)
            current.updated_at = datetime.utcnow()
            self.jobs[job_id] = current
            job = current
        await self.publish(job_id, {"type": "job.updated", "job": job.model_dump(mode="json")})

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
    await store.initialize()
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
    products: list[Product] = []
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
        products.append(product)
    await store.add_products(job.id, products)
    await store.update_job(
        job.id,
        status=JobStatus.completed,
        progress=100,
        current_product="Completed demo scrape",
        completed_products=len(products),
        remaining_products=0,
        revenue=sum(p.revenue for p in products),
        units_sold=sum(p.units_sold for p in products),
        visible_bought_count=sum(p.visible_bought_count for p in products),
        estimated_units=sum(p.units_sold for p in products if p.units_sold_estimated),
    )
