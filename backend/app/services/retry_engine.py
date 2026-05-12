"""
Intelligent retry engine with exponential backoff and circuit breaker pattern.
Features:
- Exponential backoff with jitter
- Circuit breaker for failing endpoints
- Configurable retry policies per operation
- Detailed retry telemetry
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import TypeVar, Callable, Optional, Any, Coroutine
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryStrategy(str, Enum):
    """Available retry strategies."""
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIBONACCI = "fibonacci"
    CONSTANT = "constant"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    initial_delay_ms: int = 500
    max_delay_ms: int = 30000
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    backoff_multiplier: float = 2.0
    jitter_fraction: float = 0.1  # 10% random jitter
    circuit_breaker_threshold: int = 5  # Fail X times before opening circuit
    circuit_breaker_reset_seconds: int = 60


class RetryMetrics:
    """Track retry statistics."""
    
    def __init__(self):
        self.total_attempts = 0
        self.successful_attempts = 0
        self.failed_attempts = 0
        self.circuit_breaker_trips = 0
        self.total_delay_ms = 0
        self.start_time = time.time()
    
    def add_attempt(self, success: bool, delay_ms: int = 0) -> None:
        """Record an attempt."""
        self.total_attempts += 1
        if success:
            self.successful_attempts += 1
        else:
            self.failed_attempts += 1
        self.total_delay_ms += delay_ms
    
    def get_stats(self) -> dict[str, Any]:
        """Get metrics as dictionary."""
        elapsed_seconds = time.time() - self.start_time
        return {
            "total_attempts": self.total_attempts,
            "successful": self.successful_attempts,
            "failed": self.failed_attempts,
            "success_rate": round(
                (self.successful_attempts / self.total_attempts * 100) 
                if self.total_attempts > 0 else 0, 
                2
            ),
            "circuit_trips": self.circuit_breaker_trips,
            "total_delay_seconds": round(self.total_delay_ms / 1000, 2),
            "elapsed_seconds": round(elapsed_seconds, 2),
        }


class CircuitBreaker:
    """Implement circuit breaker pattern to fail fast."""
    
    def __init__(self, failure_threshold: int = 5, reset_timeout_seconds: int = 60):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout_seconds
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open
    
    def record_success(self) -> None:
        """Record successful operation."""
        self.failure_count = 0
        self.state = "closed"
    
    def record_failure(self) -> None:
        """Record failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
    
    def can_execute(self) -> bool:
        """Check if operation can execute."""
        if self.state == "closed":
            return True
        
        if self.state == "open":
            # Check if we should try to recover
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "half_open"
                self.failure_count = 0
                return True
            return False
        
        # half_open: allow one attempt
        return True
    
    def is_open(self) -> bool:
        """Check if circuit is open."""
        if self.state == "open":
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "half_open"
                return False
            return True
        return False


class RetryEngine:
    """Intelligent retry engine with backoff strategies."""
    
    def __init__(self):
        self.config = RetryConfig()
        self.metrics = RetryMetrics()
        self.circuit_breakers: dict[str, CircuitBreaker] = {}
    
    def _calculate_delay(self, attempt: int) -> int:
        """Calculate delay in milliseconds for given attempt number."""
        if self.config.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.config.initial_delay_ms * (self.config.backoff_multiplier ** attempt)
        elif self.config.strategy == RetryStrategy.LINEAR:
            delay = self.config.initial_delay_ms * (attempt + 1)
        elif self.config.strategy == RetryStrategy.FIBONACCI:
            fib = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55]
            multiplier = fib[min(attempt, len(fib) - 1)]
            delay = self.config.initial_delay_ms * multiplier
        else:  # CONSTANT
            delay = self.config.initial_delay_ms
        
        # Cap at max delay
        delay = min(delay, self.config.max_delay_ms)
        
        # Add jitter
        jitter = delay * self.config.jitter_fraction * (random.random() * 2 - 1)
        final_delay = max(int(delay + jitter), 100)  # Minimum 100ms
        
        return final_delay
    
    def _get_circuit_breaker(self, key: str) -> CircuitBreaker:
        """Get or create circuit breaker for key."""
        if key not in self.circuit_breakers:
            self.circuit_breakers[key] = CircuitBreaker(
                failure_threshold=self.config.circuit_breaker_threshold,
                reset_timeout_seconds=self.config.circuit_breaker_reset_seconds,
            )
        return self.circuit_breakers[key]
    
    async def execute_with_retry(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *args,
        circuit_key: Optional[str] = None,
        config: Optional[RetryConfig] = None,
        **kwargs,
    ) -> T:
        """
        Execute async function with retry logic.
        
        Args:
            func: Async function to execute
            *args: Positional arguments for func
            circuit_key: Key for circuit breaker (optional)
            config: Custom retry config (uses default if None)
            **kwargs: Keyword arguments for func
        
        Returns:
            Result of function
        
        Raises:
            Exception: If all retry attempts fail
        """
        cfg = config or self.config
        
        # Check circuit breaker
        if circuit_key:
            breaker = self._get_circuit_breaker(circuit_key)
            if not breaker.can_execute():
                raise RuntimeError(f"Circuit breaker open for {circuit_key}")
        
        last_exception = None
        
        for attempt in range(cfg.max_attempts):
            try:
                result = await func(*args, **kwargs)
                
                # Success
                if circuit_key:
                    self._get_circuit_breaker(circuit_key).record_success()
                
                self.metrics.add_attempt(True)
                return result
            
            except Exception as e:
                last_exception = e
                
                # Record failure in circuit breaker
                if circuit_key:
                    self._get_circuit_breaker(circuit_key).record_failure()
                
                # Check if we should retry
                if attempt < cfg.max_attempts - 1:
                    delay_ms = self._calculate_delay(attempt)
                    self.metrics.add_attempt(False, delay_ms)
                    
                    logger.debug(
                        f"Attempt {attempt + 1}/{cfg.max_attempts} failed: {str(e)[:100]}. "
                        f"Retrying in {delay_ms}ms..."
                    )
                    
                    await asyncio.sleep(delay_ms / 1000)
                else:
                    # Last attempt failed
                    self.metrics.add_attempt(False)
                    if circuit_key:
                        self._get_circuit_breaker(circuit_key).record_failure()
        
        # All retries exhausted
        raise RuntimeError(
            f"Failed after {cfg.max_attempts} attempts: {type(last_exception).__name__}: {last_exception}"
        ) from last_exception
    
    async def execute_with_timeout_retry(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        timeout_seconds: float,
        *args,
        **kwargs,
    ) -> T:
        """Execute with timeout and automatic retry on timeout."""
        config = RetryConfig(
            max_attempts=3,
            initial_delay_ms=1000,
            strategy=RetryStrategy.LINEAR,
        )
        
        async def wrapped():
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                raise TimeoutError(f"Operation timed out after {timeout_seconds}s")
        
        return await self.execute_with_retry(
            wrapped,
            circuit_key=f"timeout_{id(func)}",
            config=config,
        )
    
    def get_metrics(self) -> dict[str, Any]:
        """Get retry metrics."""
        return self.metrics.get_stats()
    
    def reset_metrics(self) -> None:
        """Reset metrics."""
        self.metrics = RetryMetrics()


# Global retry engine instance
_retry_engine = RetryEngine()


def get_retry_engine() -> RetryEngine:
    """Get global retry engine."""
    return _retry_engine


async def retry_with_backoff(
    func: Callable[..., Coroutine[Any, Any, T]],
    *args,
    max_attempts: int = 3,
    initial_delay_ms: int = 500,
    **kwargs,
) -> T:
    """Convenience function for retrying with backoff."""
    engine = get_retry_engine()
    engine.config.max_attempts = max_attempts
    engine.config.initial_delay_ms = initial_delay_ms
    return await engine.execute_with_retry(func, *args, **kwargs)
