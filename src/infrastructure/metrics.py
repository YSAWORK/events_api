# ./src/infrastructure/metrics.py
# This module sets up Prometheus metrics for monitoring the application.


####### IMPORT TOOLS ######
# global imports
import asyncio
import time
from fastapi import Request, Response
from typing import Any, Awaitable, Callable, Optional
from aioprometheus import Counter, Histogram, Gauge
from aioprometheus.service import Service

# local imports
from src.config import get_settings


###### METRICS CONFIGURATION ######
METRICS_HOST = get_settings().METRICS_HOST
METRICS_PORT = get_settings().METRICS_PORT
METRICS_PATH = get_settings().METRICS_PATH


###### METRICS SERVICE VARIABLES ######
_service: Optional[Service] = None
_bg_task: Optional[asyncio.Task] = None
_last_total = 0.0
_last_time = time.time()
_total_events_seen = 0


###### METRICS DEFINITIONS ######
http_requests_total = Counter("http_requests_total", "Total HTTP requests")
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "Request latency in seconds",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5)
)
events_total = Counter("events_total", "Total number of processed domain events")
events_per_second = Gauge("events_per_second", "Domain events processed per second")


###### EVENTS METRICS ######
async def _update_events_per_second():
    """ Background task to update events per second metric. """
    global _last_total, _last_time
    while True:
        now_total = float(_total_events_seen)
        now_time = time.time()
        dt = max(now_time - _last_time, 1e-9)
        eps = (now_total - _last_total) / dt
        events_per_second.set({}, eps)
        _last_total = now_total
        _last_time = now_time
        await asyncio.sleep(1.0)


###### HTTP METRICS MIDDLEWARE ######
async def http_metrics_middleware(request: Request, call_next: Callable[..., Awaitable[Response]]) -> Response:
    """Starlette/FastAPI middleware: collect HTTP metrics."""
    labels = {
        "method": request.method,
        "path": request.url.path,
    }
    t0 = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - t0
    http_requests_total.inc(labels)
    http_request_duration_seconds.observe(labels, elapsed)
    return response


###### DOMAIN EVENT METRICS ######
def record_event(labels: dict[str, Any] | None = None) -> None:
    """ Record a domain event occurrence."""
    global _total_events_seen
    _total_events_seen += 1
    events_total.inc(labels or {})
    events_total.inc({})


def time_block() -> Callable[[], float]:
    """ Simple timer for measuring elapsed time of a code block."""
    start = time.perf_counter()

    def _stop() -> float:
        return time.perf_counter() - start

    return _stop


def time_and_record_histogram(
    labels: dict[str, Any] | None = None
) -> Callable[[], float]:
    """ Time a code block and record the duration in the HTTP request duration histogram."""
    stop = time_block()

    def _stop_and_record() -> float:
        elapsed = stop()
        http_request_duration_seconds.observe(labels or {}, elapsed)
        return elapsed

    return _stop_and_record
