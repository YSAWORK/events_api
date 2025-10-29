# ./tests/test_infrastructure/test_metrics.py


###### IMPORT TOOLS ######
# global imports
import asyncio
import time
from types import SimpleNamespace
import pytest

# local imports
import src.infrastructure.metrics as metrics
from starlette.responses import Response


###### TESTS ######
def test_record_event_increments_and_double_inc(monkeypatch):
    """record_event should increase internal counter and call events_total.inc twice."""
    calls = []

    def _inc(labels):
        calls.append(labels)

    monkeypatch.setattr(metrics.events_total, "inc", _inc, raising=True)
    old_total = metrics._total_events_seen
    try:
        metrics._total_events_seen = 0
        metrics.record_event({"k": "v"})
        assert metrics._total_events_seen == 1
        assert calls == [{"k": "v"}, {}]
    finally:
        metrics._total_events_seen = old_total


def test_time_block_returns_elapsed_positive():
    """time_block should return a stopper callable that yields non-negative elapsed time."""
    stop = metrics.time_block()
    time.sleep(0.001)
    elapsed = stop()
    assert isinstance(elapsed, float)
    assert elapsed >= 0.0


def test_time_and_record_histogram_records(monkeypatch):
    """time_and_record_histogram should observe duration in the histogram with provided labels."""
    observed = []

    def _observe(labels, value):
        observed.append((labels, value))

    monkeypatch.setattr(metrics.http_request_duration_seconds, "observe", _observe, raising=True)
    stop = metrics.time_and_record_histogram({"op": "foo"})
    time.sleep(0.001)
    elapsed = stop()
    assert len(observed) == 1
    labels, val = observed[0]
    assert labels == {"op": "foo"}
    assert isinstance(val, float) and val >= 0.0
    assert isinstance(elapsed, float) and elapsed >= 0.0


@pytest.mark.asyncio
async def test_http_metrics_middleware_counts(monkeypatch):
    """Middleware should increment http_requests_total and observe latency histogram with correct labels."""
    inc_calls = []
    obs_calls = []

    def _inc(labels):
        inc_calls.append(labels)

    def _observe(labels, value):
        obs_calls.append((labels, value))

    monkeypatch.setattr(metrics.http_requests_total, "inc", _inc, raising=True)
    monkeypatch.setattr(metrics.http_request_duration_seconds, "observe", _observe, raising=True)
    req = SimpleNamespace(method="GET", url=SimpleNamespace(path="/test-path"))

    async def call_next(_request):
        await asyncio.sleep(0)
        return Response(content=b"ok", media_type="text/plain")

    resp = await metrics.http_metrics_middleware(req, call_next)
    assert resp.status_code == 200
    assert inc_calls == [{"method": "GET", "path": "/test-path"}]
    assert len(obs_calls) == 1
    labels, value = obs_calls[0]
    assert labels == {"method": "GET", "path": "/test-path"}
    assert isinstance(value, float) and value >= 0.0


@pytest.mark.asyncio
async def test_update_events_per_second_sets_gauge_once(monkeypatch):
    """_update_events_per_second should compute EPS and set the gauge; we stop the loop after first iteration."""
    sets = []

    def _set(labels, value):
        sets.append((labels, value))

    async def _sleep(_seconds):
        raise asyncio.CancelledError


    monkeypatch.setattr(metrics.events_per_second, "set", _set, raising=True)
    monkeypatch.setattr(asyncio, "sleep", _sleep, raising=True)
    old_last_total = metrics._last_total
    old_last_time = metrics._last_time
    old_total_seen = metrics._total_events_seen
    try:
        metrics._last_total = 0.0
        metrics._last_time = time.time() - 1.0
        metrics._total_events_seen = 5
        with pytest.raises(asyncio.CancelledError):
            await metrics._update_events_per_second()

        assert len(sets) >= 1
        labels, val = sets[0]
        assert labels == {}
        assert isinstance(val, float)
    finally:
        metrics._last_total = old_last_total
        metrics._last_time = old_last_time
        metrics._total_events_seen = old_total_seen
