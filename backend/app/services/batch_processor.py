"""
Batch URL processor for scraping multiple URLs concurrently with intelligent scheduling.
Features:
- Concurrent URL processing
- Rate limiting per domain
- Smart batching and queue management
- Progress tracking
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class JobPriority(str, Enum):
    """Job priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class BatchJob:
    """Single batch job entry."""
    url: str
    job_id: str
    priority: JobPriority = JobPriority.NORMAL
    created_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 2
    result: Optional[Any] = None
    error: Optional[str] = None
    status: str = "queued"  # queued, processing, completed, failed
    
    def __lt__(self, other: BatchJob) -> bool:
        """For priority queue ordering (higher priority first, then by creation time)."""
        priority_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
        if priority_order[self.priority] != priority_order[other.priority]:
            return priority_order[self.priority] < priority_order[other.priority]
        return self.created_at < other.created_at


class DomainRateLimiter:
    """Rate limiter per domain to avoid overwhelming single sites."""
    
    def __init__(self, requests_per_second: float = 1.0, requests_per_minute: int = 30):
        self.requests_per_second = requests_per_second
        self.requests_per_minute = requests_per_minute
        self.min_interval_sec = 1.0 / requests_per_second
        
        self.domain_last_request: dict[str, float] = {}
        self.domain_requests_in_window: dict[str, list[float]] = defaultdict(list)
        self.lock = asyncio.Lock()
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        from urllib.parse import urlparse
        return urlparse(url).netloc or url
    
    async def wait_if_needed(self, url: str) -> None:
        """Wait if rate limit would be exceeded."""
        async with self.lock:
            domain = self._extract_domain(url)
            now = time.time()
            
            # Check per-second limit
            last_request = self.domain_last_request.get(domain, 0)
            time_since_last = now - last_request
            
            if time_since_last < self.min_interval_sec:
                wait_time = self.min_interval_sec - time_since_last
                logger.debug(f"Rate limiting {domain}: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
            
            # Check per-minute limit
            window_times = self.domain_requests_in_window[domain]
            cutoff_time = now - 60
            
            # Clean old requests
            window_times = [t for t in window_times if t > cutoff_time]
            self.domain_requests_in_window[domain] = window_times
            
            if len(window_times) >= self.requests_per_minute:
                wait_time = 60 - (now - window_times[0]) + 1
                logger.debug(f"Per-minute rate limit for {domain}: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
            
            # Record this request
            self.domain_requests_in_window[domain].append(now)
            self.domain_last_request[domain] = time.time()


class BatchProcessor:
    """Process multiple URLs efficiently with rate limiting and priority."""
    
    def __init__(
        self,
        max_concurrent_jobs: int = 3,
        requests_per_second_per_domain: float = 1.0,
        requests_per_minute_per_domain: int = 30,
    ):
        self.max_concurrent_jobs = max_concurrent_jobs
        self.rate_limiter = DomainRateLimiter(
            requests_per_second=requests_per_second_per_domain,
            requests_per_minute=requests_per_minute_per_domain,
        )
        
        self.job_queue: list[BatchJob] = []
        self.active_jobs: dict[str, BatchJob] = {}
        self.completed_jobs: dict[str, BatchJob] = {}
        self.failed_jobs: dict[str, BatchJob] = {}
        
        self.lock = asyncio.Lock()
        self.semaphore = asyncio.Semaphore(max_concurrent_jobs)
        self.stats = {
            "total_queued": 0,
            "total_processed": 0,
            "total_succeeded": 0,
            "total_failed": 0,
            "start_time": None,
        }
    
    async def add_job(
        self,
        url: str,
        job_id: str,
        priority: JobPriority = JobPriority.NORMAL,
    ) -> BatchJob:
        """Add URL to batch queue."""
        async with self.lock:
            job = BatchJob(url=url, job_id=job_id, priority=priority)
            self.job_queue.append(job)
            self.job_queue.sort()  # Sort by priority
            self.stats["total_queued"] += 1
            
            if self.stats["start_time"] is None:
                self.stats["start_time"] = time.time()
            
            logger.info(f"Added job {job_id}: {url[:50]}... (priority: {priority})")
            return job
    
    async def add_batch(
        self,
        urls: list[str],
        job_prefix: str = "batch",
        priority: JobPriority = JobPriority.NORMAL,
    ) -> list[BatchJob]:
        """Add multiple URLs to batch queue."""
        jobs = []
        for i, url in enumerate(urls):
            job_id = f"{job_prefix}_{i}"
            job = await self.add_job(url, job_id, priority)
            jobs.append(job)
        return jobs
    
    async def process_batch(
        self,
        process_func: Callable[[str, str], Any],
    ) -> dict[str, Any]:
        """
        Process all queued jobs.
        
        Args:
            process_func: Async function(url, job_id) that processes a URL
        
        Returns:
            Results dictionary with completed, failed, stats
        """
        logger.info(f"Starting batch processing: {len(self.job_queue)} jobs, {self.max_concurrent_jobs} concurrent")
        
        tasks = []
        for job in self.job_queue:
            task = asyncio.create_task(
                self._process_single_job(job, process_func)
            )
            tasks.append(task)
        
        # Wait for all tasks
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Compile results
        return {
            "total_queued": self.stats["total_queued"],
            "completed": len(self.completed_jobs),
            "failed": len(self.failed_jobs),
            "success_rate": round(
                (len(self.completed_jobs) / self.stats["total_queued"] * 100)
                if self.stats["total_queued"] > 0
                else 0,
                2,
            ),
            "elapsed_seconds": round(time.time() - self.stats["start_time"], 2) if self.stats["start_time"] else 0,
            "completed_jobs": self.completed_jobs,
            "failed_jobs": self.failed_jobs,
        }
    
    async def _process_single_job(
        self,
        job: BatchJob,
        process_func: Callable[[str, str], Any],
    ) -> None:
        """Process single job with rate limiting and retry."""
        async with self.semaphore:
            try:
                # Rate limiting
                await self.rate_limiter.wait_if_needed(job.url)
                
                # Update status
                async with self.lock:
                    job.status = "processing"
                    self.active_jobs[job.job_id] = job
                
                logger.info(f"Processing job {job.job_id}: {job.url[:60]}...")
                
                # Process with retry
                result = await self._execute_with_retry(job, process_func)
                
                # Mark completed
                async with self.lock:
                    job.status = "completed"
                    job.result = result
                    self.completed_jobs[job.job_id] = job
                    self.active_jobs.pop(job.job_id, None)
                    self.stats["total_succeeded"] += 1
                
                logger.info(f"✅ Completed job {job.job_id}")
            
            except Exception as e:
                logger.error(f"❌ Failed job {job.job_id}: {e}")
                
                async with self.lock:
                    job.status = "failed"
                    job.error = str(e)
                    self.failed_jobs[job.job_id] = job
                    self.active_jobs.pop(job.job_id, None)
                    self.stats["total_failed"] += 1
    
    async def _execute_with_retry(
        self,
        job: BatchJob,
        process_func: Callable[[str, str], Any],
    ) -> Any:
        """Execute job with retry logic."""
        last_error = None
        
        for attempt in range(job.max_retries + 1):
            try:
                result = await process_func(job.url, job.job_id)
                return result
            
            except Exception as e:
                last_error = e
                job.retry_count = attempt + 1
                
                if attempt < job.max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(
                        f"Job {job.job_id} attempt {attempt + 1} failed, retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)
        
        raise RuntimeError(f"Job failed after {job.max_retries + 1} attempts: {last_error}")
    
    async def get_status(self) -> dict[str, Any]:
        """Get batch processor status."""
        async with self.lock:
            return {
                "queued": len(self.job_queue),
                "active": len(self.active_jobs),
                "completed": len(self.completed_jobs),
                "failed": len(self.failed_jobs),
                "success_rate": round(
                    (len(self.completed_jobs) / (len(self.completed_jobs) + len(self.failed_jobs)) * 100)
                    if (len(self.completed_jobs) + len(self.failed_jobs)) > 0
                    else 0,
                    2,
                ),
                "stats": self.stats,
            }
    
    async def clear(self) -> None:
        """Clear all jobs."""
        async with self.lock:
            self.job_queue.clear()
            self.active_jobs.clear()
            self.completed_jobs.clear()
            self.failed_jobs.clear()
            self.stats = {
                "total_queued": 0,
                "total_processed": 0,
                "total_succeeded": 0,
                "total_failed": 0,
                "start_time": None,
            }


# Global batch processor
_batch_processor = BatchProcessor(
    max_concurrent_jobs=3,
    requests_per_second_per_domain=1.0,
    requests_per_minute_per_domain=30,
)


def get_batch_processor() -> BatchProcessor:
    """Get global batch processor."""
    return _batch_processor
