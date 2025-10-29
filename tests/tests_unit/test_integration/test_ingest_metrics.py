# tests/tests_unit/test_integration/test_ingest_metrics.py
import os
import uuid
import pytest
from datetime import datetime, timedelta, date

from httpx import AsyncClient, ASGITransport


def _resolve_app(maybe_app):
    obj = maybe_app
    if callable(obj) and not getattr(obj, "router", None):
        obj = obj()
    if isinstance(obj, (tuple, list)) and obj:
        obj = obj[0]
    if isinstance(obj, dict) and "app" in obj:
        obj = obj["app"]
    assert getattr(obj, "router", None) is not None, f"fresh_app_factory did not yield a FastAPI app. Got: {type(obj)!r}"
    return obj


def _extract_series(obj):
    if isinstance(obj, dict):
        inner = None
        for key in ("items", "data", "results"):
            if key in obj:
                inner = obj[key]; break
        if inner is None:
            out = {}
            for k, v in obj.items():
                try:
                    out[date.fromisoformat(str(k))] = int(v)
                except Exception:
                    pass
            if out:
                return out
            raise AssertionError("Unrecognized DAU response shape (dict).")
        obj = inner
    if isinstance(obj, list):
        out = {}
        for row in obj:
            d_raw = row.get("day") or row.get("date") or row.get("occurred_date")
            dau_raw = row.get("dau") or row.get("count") or row.get("value")
            assert d_raw is not None, f"Missing day/date key in {row}"
            assert dau_raw is not None, f"Missing dau/count key in {row}"
            out[date.fromisoformat(str(d_raw))] = int(dau_raw)
        return out
    raise AssertionError("Unrecognized DAU response type.")


@pytest.mark.asyncio
async def test_ingest_then_query_dau(patched_main_env, fresh_app_factory):
    """Integration path: ingest events -> query /stats/dau, without lifespan to avoid FakeEngine.dispose()."""
    app = _resolve_app(fresh_app_factory)

    headers = {"X-Benchmark-Token": os.getenv("BENCHMARK_TOKEN", "TEST_TOKEN_VALUE")}

    day0 = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    day1 = day0 + timedelta(days=1)

    payload = [
        {"event_id": str(uuid.uuid4()), "occurred_at": day0.isoformat(), "user_id": 1, "event_type": "app_open", "properties": {"country": "UA"}},
        {"event_id": str(uuid.uuid4()), "occurred_at": day0.isoformat(), "user_id": 2, "event_type": "view_item", "properties": {"country": "UA"}},
        {"event_id": str(uuid.uuid4()), "occurred_at": day1.isoformat(), "user_id": 1, "event_type": "login", "properties": {"country": "UA"}},
        {"event_id": str(uuid.uuid4()), "occurred_at": day1.isoformat(), "user_id": 3, "event_type": "purchase", "properties": {"country": "UA"}},
        {"event_id": str(uuid.uuid4()), "occurred_at": day1.isoformat(), "user_id": 4, "event_type": "app_open", "properties": {"country": "UA"}},
    ]
    expected = {day0.date(): 2, day1.date(): 3}

    # No LifespanManager here; older httpx also doesn't auto-run lifespan.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r_ingest = await client.post("/events/", json=payload, headers=headers)
        assert r_ingest.status_code in (200, 201), r_ingest.text

        q_from, q_to = day0.date().isoformat(), day1.date().isoformat()
        r_dau = await client.get(f"/stats/dau?from={q_from}&to={q_to}", headers=headers)
        assert r_dau.status_code == 200, r_dau.text

        series = _extract_series(r_dau.json())

    for d, dau in expected.items():
        assert d in series, f"Missing day {d} in DAU response: {series}"
        assert series[d] == dau, f"DAU mismatch for {d}: got {series[d]}, expected {dau}"
