"""
Performance monitoring and metrics collection for scraping jobs.
Features:
- Real-time performance metrics
- Bottleneck detection
- Efficiency scoring
- Timeline tracking
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from collections import defaultdict


@dataclass
class PerformanceMetrics:
    """Performance metrics for a scraping job."""
    job_id: str
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    
    # Timing metrics (in seconds)
    initialization_time: float = 0.0
    page_load_time: float = 0.0
    extraction_time: float = 0.0
    detail_enrichment_time: float = 0.0
    product_saving_time: float = 0.0
    
    # Data metrics
    total_products: int = 0
    products_per_second: float = 0.0
    
    # Resource metrics
    browser_instances_used: int = 1
    parallel_detail_fetches: int = 4
    
    def calculate_total_time(self) -> float:
        """Calculate total execution time in seconds."""
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()
    
    def calculate_efficiency(self) -> float:
        """Calculate efficiency score (products per second)."""
        total_time = self.calculate_total_time()
        if total_time <= 0:
            return 0.0
        return self.total_products / total_time
    
    def identify_bottlenecks(self) -> list[tuple[str, float]]:
        """Identify processing bottlenecks."""
        timings = [
            ("Initialization", self.initialization_time),
            ("Page Load", self.page_load_time),
            ("Extraction", self.extraction_time),
            ("Detail Enrichment", self.detail_enrichment_time),
            ("Product Saving", self.product_saving_time),
        ]
        # Return sorted by duration
        return sorted([t for t in timings if t[1] > 0], key=lambda x: x[1], reverse=True)
    
    def get_report(self) -> dict:
        """Generate performance report."""
        total_time = self.calculate_total_time()
        efficiency = self.calculate_efficiency()
        bottlenecks = self.identify_bottlenecks()
        
        return {
            "job_id": self.job_id,
            "total_time_seconds": round(total_time, 2),
            "total_products_extracted": self.total_products,
            "products_per_second": round(efficiency, 2),
            "initialization_time": self.initialization_time,
            "page_load_time": self.page_load_time,
            "extraction_time": self.extraction_time,
            "detail_enrichment_time": self.detail_enrichment_time,
            "product_saving_time": self.product_saving_time,
            "browser_instances": self.browser_instances_used,
            "parallel_detail_fetches": self.parallel_detail_fetches,
            "bottlenecks": [{"stage": name, "duration": round(duration, 2)} for name, duration in bottlenecks],
            "estimated_improvement_with_async": self._estimate_improvement(),
        }
    
    def _estimate_improvement(self) -> dict:
        """Estimate performance improvement with async operations."""
        # Calculate what would be saved with full parallelization
        sequential_time = self.calculate_total_time()
        
        # Assume detail enrichment can be 3x faster with parallelization
        detail_improvement = self.detail_enrichment_time * 0.66
        
        # Assume product saving can be 2x faster with batch operations
        saving_improvement = self.product_saving_time * 0.5
        
        total_improvement = detail_improvement + saving_improvement
        improved_time = max(sequential_time - total_improvement, sequential_time * 0.6)  # At least 40% of original
        
        return {
            "estimated_improvement_seconds": round(total_improvement, 2),
            "estimated_new_total_time": round(improved_time, 2),
            "speedup_factor": round(sequential_time / improved_time, 2) if improved_time > 0 else 1.0,
        }


class MetricsCollector:
    """Collect and track performance metrics across jobs."""
    
    def __init__(self):
        self.job_metrics: dict[str, PerformanceMetrics] = {}
        self.historical_metrics: list[PerformanceMetrics] = []
        self._timers: dict[str, dict] = defaultdict(dict)
    
    def start_job(self, job_id: str) -> PerformanceMetrics:
        """Start tracking metrics for a job."""
        metrics = PerformanceMetrics(job_id)
        self.job_metrics[job_id] = metrics
        return metrics
    
    def end_job(self, job_id: str):
        """End tracking for a job."""
        if job_id in self.job_metrics:
            metrics = self.job_metrics[job_id]
            metrics.end_time = datetime.now()
            self.historical_metrics.append(metrics)
    
    def start_timer(self, job_id: str, phase: str):
        """Start a timer for a phase."""
        self._timers[job_id][phase] = time.time()
    
    def end_timer(self, job_id: str, phase: str) -> float:
        """End a timer and return elapsed time."""
        if job_id not in self._timers or phase not in self._timers[job_id]:
            return 0.0
        
        elapsed = time.time() - self._timers[job_id][phase]
        del self._timers[job_id][phase]
        
        if job_id in self.job_metrics:
            metrics = self.job_metrics[job_id]
            if phase == "initialization":
                metrics.initialization_time = elapsed
            elif phase == "page_load":
                metrics.page_load_time = elapsed
            elif phase == "extraction":
                metrics.extraction_time = elapsed
            elif phase == "detail_enrichment":
                metrics.detail_enrichment_time = elapsed
            elif phase == "product_saving":
                metrics.product_saving_time = elapsed
        
        return elapsed
    
    def record_product_count(self, job_id: str, count: int):
        """Record number of products extracted."""
        if job_id in self.job_metrics:
            self.job_metrics[job_id].total_products = count
    
    def get_job_report(self, job_id: str) -> Optional[dict]:
        """Get performance report for a job."""
        if job_id in self.job_metrics:
            return self.job_metrics[job_id].get_report()
        return None
    
    def get_average_metrics(self) -> dict:
        """Get average metrics across all historical jobs."""
        if not self.historical_metrics:
            return {}
        
        total_time = sum(m.calculate_total_time() for m in self.historical_metrics)
        total_products = sum(m.total_products for m in self.historical_metrics)
        avg_efficiency = sum(m.calculate_efficiency() for m in self.historical_metrics) / len(self.historical_metrics)
        
        return {
            "jobs_processed": len(self.historical_metrics),
            "average_job_time": round(total_time / len(self.historical_metrics), 2),
            "average_efficiency": round(avg_efficiency, 2),
            "total_products_extracted": total_products,
            "total_processing_time": round(total_time, 2),
        }
    
    def get_timeline_analysis(self) -> dict:
        """Get timeline analysis of recent jobs."""
        recent = self.historical_metrics[-10:]  # Last 10 jobs
        if not recent:
            return {}
        
        timeline = {
            "recent_jobs": len(recent),
            "efficiency_trend": [m.calculate_efficiency() for m in recent],
            "average_efficiency": sum(m.calculate_efficiency() for m in recent) / len(recent),
            "fastest_job": min((m.calculate_total_time(), m.job_id) for m in recent),
            "slowest_job": max((m.calculate_total_time(), m.job_id) for m in recent),
        }
        
        return timeline


# Global metrics collector
_metrics_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector."""
    return _metrics_collector
