"""
Optimized job queue system with worker pools and concurrent processing.
Features:
- Background worker pools for concurrent job processing
- Priority queue for jobs
- Worker health monitoring
- Graceful shutdown
- Real-time progress updates
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional
from datetime import datetime

from backend.app.schemas import Job, JobStatus, ScrapeRequest


class JobPriority(Enum):
    """Job priority levels."""
    LOW = 3
    NORMAL = 2
    HIGH = 1
    URGENT = 0


@dataclass
class QueuedJob:
    """A job in the queue."""
    job_id: str
    request: ScrapeRequest
    priority: JobPriority = JobPriority.NORMAL
    created_at: datetime = field(default_factory=datetime.now)
    retries: int = 0
    max_retries: int = 2
    
    def __lt__(self, other: QueuedJob) -> bool:
        """Compare by priority, then by creation time."""
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return self.created_at < other.created_at


class JobQueue:
    """Priority queue for scraping jobs."""
    
    def __init__(self, max_workers: int = 3, worker_timeout: int = 3600):
        self.max_workers = max_workers
        self.worker_timeout = worker_timeout
        self.queue: asyncio.PriorityQueue[QueuedJob] = asyncio.PriorityQueue()
        self.active_jobs: dict[str, asyncio.Task] = {}
        self.completed_jobs: set[str] = set()
        self.failed_jobs: dict[str, str] = {}
        self.workers: list[asyncio.Task] = []
        self._lock = asyncio.Lock()
        self._shutdown = False
        self._job_counter = 0
    
    async def enqueue(self, job_id: str, request: ScrapeRequest, priority: JobPriority = JobPriority.NORMAL):
        """Add a job to the queue."""
        async with self._lock:
            self._job_counter += 1
            queued_job = QueuedJob(job_id, request, priority)
            await self.queue.put((queued_job.priority.value, self._job_counter, queued_job))
    
    async def start_workers(self, worker_func: Callable[[str, ScrapeRequest], asyncio.Task]):
        """Start background workers to process jobs."""
        for _ in range(self.max_workers):
            worker = asyncio.create_task(self._worker_loop(worker_func))
            self.workers.append(worker)
    
    async def _worker_loop(self, worker_func: Callable[[str, ScrapeRequest], asyncio.Task]):
        """Process jobs from the queue continuously."""
        while not self._shutdown:
            try:
                try:
                    _, _, queued_job = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
                
                async with self._lock:
                    if queued_job.job_id in self.active_jobs:
                        continue  # Skip if already running
                    
                    # Create task and track it
                    task = asyncio.create_task(worker_func(queued_job.job_id, queued_job.request))
                    self.active_jobs[queued_job.job_id] = task
                
                # Wait for job with timeout
                try:
                    await asyncio.wait_for(task, timeout=self.worker_timeout)
                    async with self._lock:
                        self.completed_jobs.add(queued_job.job_id)
                        self.active_jobs.pop(queued_job.job_id, None)
                except asyncio.TimeoutError:
                    async with self._lock:
                        task.cancel()
                        self.failed_jobs[queued_job.job_id] = "Job timeout"
                        self.active_jobs.pop(queued_job.job_id, None)
                    with suppress(asyncio.CancelledError):
                        await task
                except asyncio.CancelledError:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                    async with self._lock:
                        self.active_jobs.pop(queued_job.job_id, None)
                    break
                except Exception as e:
                    if queued_job.retries < queued_job.max_retries:
                        # Retry with lower priority
                        queued_job.retries += 1
                        await self.enqueue(
                            queued_job.job_id,
                            queued_job.request,
                            JobPriority.LOW if queued_job.priority == JobPriority.NORMAL else JobPriority.LOW
                        )
                    else:
                        async with self._lock:
                            self.failed_jobs[queued_job.job_id] = str(e)
                        async with self._lock:
                            self.active_jobs.pop(queued_job.job_id, None)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                await asyncio.sleep(0.1)
    
    async def shutdown(self):
        """Gracefully shutdown the queue and workers."""
        self._shutdown = True
        async with self._lock:
            active_tasks = list(self.active_jobs.values())
            self.active_jobs.clear()
        for task in active_tasks:
            task.cancel()
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
    
    def get_status(self) -> dict:
        """Get queue status."""
        return {
            "active_jobs": len(self.active_jobs),
            "completed_jobs": len(self.completed_jobs),
            "failed_jobs": len(self.failed_jobs),
            "pending_jobs": self.queue.qsize(),
            "workers": len(self.workers),
            "active_job_ids": list(self.active_jobs.keys()),
        }
    
    async def is_job_running(self, job_id: str) -> bool:
        """Check if a job is currently running."""
        async with self._lock:
            return job_id in self.active_jobs
    
    async def is_job_completed(self, job_id: str) -> bool:
        """Check if a job has completed."""
        async with self._lock:
            return job_id in self.completed_jobs
    
    async def get_job_error(self, job_id: str) -> Optional[str]:
        """Get error message if job failed."""
        async with self._lock:
            return self.failed_jobs.get(job_id)


# Global job queue instance
_job_queue: Optional[JobQueue] = None


async def get_job_queue() -> JobQueue:
    """Get or create the global job queue."""
    global _job_queue
    if _job_queue is None:
        _job_queue = JobQueue(max_workers=3, worker_timeout=3600)
    return _job_queue


async def initialize_job_queue(worker_func: Callable[[str, ScrapeRequest], asyncio.Task]):
    """Initialize the job queue with worker function."""
    queue = await get_job_queue()
    await queue.start_workers(worker_func)


async def shutdown_job_queue():
    """Shutdown the job queue."""
    global _job_queue
    if _job_queue:
        await _job_queue.shutdown()
        _job_queue = None
