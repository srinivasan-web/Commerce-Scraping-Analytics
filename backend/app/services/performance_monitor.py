"""
Performance monitoring and optimization tracking for the scraper.
Features:
- Real-time performance metrics
- Optimization impact analysis
- Cache hit/miss tracking
- Retry statistics
"""

from __future__ import annotations

import time
import logging
from typing import Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Track performance for a single scraping job."""
    job_id: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    
    # Timing
    page_load_time_ms: int = 0
    extraction_time_ms: int = 0
    detail_fetch_time_ms: int = 0
    variant_expansion_time_ms: int = 0
    total_time_ms: int = 0
    
    # Caching
    cache_hit: bool = False
    cache_time_saved_ms: int = 0
    
    # Extraction
    products_extracted: int = 0
    unique_products: int = 0
    duplicates_detected: int = 0
    
    # Retries
    total_retry_attempts: int = 0
    successful_retries: int = 0
    failed_retries: int = 0
    
    # Parallel processing
    parallel_batches_processed: int = 0
    failed_parallel_operations: int = 0
    
    def finish(self) -> None:
        """Mark completion and calculate total time."""
        self.end_time = time.time()
        self.total_time_ms = int((self.end_time - self.start_time) * 1000)
    
    def get_optimization_savings(self) -> dict[str, Any]:
        """Calculate time saved by optimizations."""
        savings = {
            "cache_savings_ms": self.cache_time_saved_ms if self.cache_hit else 0,
            "parallel_processing_efficiency": round(
                (self.detail_fetch_time_ms + self.variant_expansion_time_ms) / max(self.total_time_ms, 1) * 100,
                2,
            ),
            "retry_success_rate": round(
                (self.successful_retries / max(self.total_retry_attempts, 1) * 100),
                2,
            ) if self.total_retry_attempts > 0 else 0,
        }
        return savings
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "job_id": self.job_id,
            "total_time_seconds": round(self.total_time_ms / 1000, 2),
            "page_load_seconds": round(self.page_load_time_ms / 1000, 2),
            "extraction_seconds": round(self.extraction_time_ms / 1000, 2),
            "detail_fetch_seconds": round(self.detail_fetch_time_ms / 1000, 2),
            "variant_expansion_seconds": round(self.variant_expansion_time_ms / 1000, 2),
            "cache_hit": self.cache_hit,
            "cache_savings_seconds": round(self.cache_time_saved_ms / 1000, 2),
            "products_extracted": self.products_extracted,
            "unique_products": self.unique_products,
            "duplicates_detected": self.duplicates_detected,
            "retry_attempts": self.total_retry_attempts,
            "successful_retries": self.successful_retries,
            "parallel_batches": self.parallel_batches_processed,
            "optimization_savings": self.get_optimization_savings(),
        }


class PerformanceMonitor:
    """Monitor and analyze performance across jobs."""
    
    def __init__(self):
        self.current_job_metrics: dict[str, PerformanceMetrics] = {}
        self.completed_metrics: list[PerformanceMetrics] = []
        self.max_history = 100
    
    def start_job(self, job_id: str) -> PerformanceMetrics:
        """Start tracking metrics for a job."""
        metrics = PerformanceMetrics(job_id=job_id)
        self.current_job_metrics[job_id] = metrics
        return metrics
    
    def end_job(self, job_id: str) -> Optional[PerformanceMetrics]:
        """Finish tracking metrics for a job."""
        if job_id not in self.current_job_metrics:
            return None
        
        metrics = self.current_job_metrics.pop(job_id)
        metrics.finish()
        
        # Store in history
        self.completed_metrics.append(metrics)
        if len(self.completed_metrics) > self.max_history:
            self.completed_metrics.pop(0)
        
        logger.info(f"Job {job_id} completed: {metrics.to_dict()}")
        return metrics
    
    def get_job_metrics(self, job_id: str) -> Optional[PerformanceMetrics]:
        """Get metrics for a specific job."""
        return self.current_job_metrics.get(job_id) or next(
            (m for m in self.completed_metrics if m.job_id == job_id),
            None,
        )
    
    def get_average_metrics(self) -> dict[str, Any]:
        """Get average metrics across all completed jobs."""
        if not self.completed_metrics:
            return {}
        
        total_jobs = len(self.completed_metrics)
        avg_time = sum(m.total_time_ms for m in self.completed_metrics) / total_jobs
        avg_products = sum(m.products_extracted for m in self.completed_metrics) / total_jobs
        cache_hits = sum(1 for m in self.completed_metrics if m.cache_hit)
        
        return {
            "average_job_time_seconds": round(avg_time / 1000, 2),
            "average_products_per_job": round(avg_products, 1),
            "cache_hit_rate_percent": round(cache_hits / total_jobs * 100, 2),
            "total_jobs_monitored": total_jobs,
            "total_cache_time_saved_seconds": round(
                sum(m.cache_time_saved_ms for m in self.completed_metrics) / 1000, 2
            ),
        }
    
    def get_optimization_impact(self) -> dict[str, Any]:
        """Calculate impact of all optimizations."""
        if not self.completed_metrics:
            return {}
        
        total_time = sum(m.total_time_ms for m in self.completed_metrics)
        total_cache_saved = sum(m.cache_time_saved_ms for m in self.completed_metrics)
        total_products = sum(m.products_extracted for m in self.completed_metrics)
        total_retries = sum(m.total_retry_attempts for m in self.completed_metrics)
        successful_retries = sum(m.successful_retries for m in self.completed_metrics)
        
        return {
            "total_jobs_completed": len(self.completed_metrics),
            "total_processing_time_seconds": round(total_time / 1000, 2),
            "total_cache_savings_seconds": round(total_cache_saved / 1000, 2),
            "cache_savings_percent": round(
                (total_cache_saved / max(total_time, 1) * 100), 2
            ),
            "total_products_extracted": total_products,
            "avg_products_per_second": round(
                total_products / max(total_time / 1000, 1), 2
            ),
            "retry_success_rate": round(
                (successful_retries / max(total_retries, 1) * 100), 2
            ) if total_retries > 0 else 0,
            "estimated_time_saved_vs_sequential": round(
                (total_time * 0.4), 2  # Assuming 40% time saved from parallelization
            ),
        }
    
    def reset(self) -> None:
        """Reset all metrics."""
        self.current_job_metrics.clear()
        self.completed_metrics.clear()


# Global performance monitor
_perf_monitor = PerformanceMonitor()


def get_performance_monitor() -> PerformanceMonitor:
    """Get global performance monitor."""
    return _perf_monitor


def start_monitoring(job_id: str) -> PerformanceMetrics:
    """Start monitoring a job."""
    return get_performance_monitor().start_job(job_id)


def end_monitoring(job_id: str) -> Optional[PerformanceMetrics]:
    """End monitoring a job."""
    return get_performance_monitor().end_job(job_id)


def get_metrics(job_id: str) -> Optional[PerformanceMetrics]:
    """Get metrics for a job."""
    return get_performance_monitor().get_job_metrics(job_id)
