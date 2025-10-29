import pytest
from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager

# Module under test
from src.endpoint_events import routers as events_routers


# ---------- Fakes & helpers ----------

class FakeResult:
    def __init__(self, rows):
        self._rows = rows
    def fetchall(self):
        return self._rows


class FakeAsyncSession:
    """Minimal async session stub used to intercept execute/commit calls."""
    def __init__(self, rows_to_return):
        self._rows_to_return = rows_to_return
        self.exec_calls = []
        self.commits = 0

    async def execute(self, stmt):
        self.exec_calls.append(stmt)
        return FakeResult(self._rows_to_return)

    async def commit(self):
        self.commits += 1


def _norm_ids(iterable):
    """Normalize IDs to lowercase strings for robust comparisons."""
    return {str(x).lower() for x in iterable}


@pytest.fixture
def make_app(monkeypatch):
    """
    Build a minimal FastAPI app with the router under test and:
      - override events_routers.resources.get_session -> FakeAsyncSession (IMPORTANT)
      - override record_event -> spy collector
      - neutralize all route-level Depends(...) (e.g., RateLimiter) with a NO-ARG no-op
    """
    from fastapi import FastAPI

    def _noop_dep():
        # MUST take no params; regular def avoids FastAPI treating args as query params
        return None

    def _factory(rows_to_return):
        app = FastAPI()

        # Spy for metrics
        calls = {"record_event": []}
        monkeypatch.setattr(
            events_routers, "record_event",
            lambda payload: calls["record_event"].append(payload),
            raising=True,
        )

        # Provide fake DB session by patching the *imported instance* in the router module
        fake_db = FakeAsyncSession(rows_to_return)
        monkeypatch.setattr(
            events_routers.resources, "get_session",
            lambda: fake_db,
            raising=True,
        )

        # Mount router
        app.include_router(events_routers.router)

        # Neutralize exact dependency callables captured on routes (e.g., RateLimiter)
        for route in app.router.routes:
            for dep in getattr(route, "dependencies", []) or []:
                if getattr(dep, "dependency", None):
                    app.dependency_overrides[dep.dependency] = _noop_dep

        return app, fake_db, calls

    return _factory


# Valid UUIDs for payloads
A = "11111111-1111-1111-1111-111111111111"
B = "22222222-2222-2222-2222-222222222222"
C = "33333333-3333-3333-3333-333333333333"
X = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


# ---------- Tests ----------

@pytest.mark.asyncio
async def test_add_unique_events_inserts_and_marks_duplicates(make_app):
    """
    Given input [A, B, C] and DB returns inserted (A, C),
    API must mark B as duplicate and commit exactly once.
    """
    app, fake_db, calls = make_app(rows_to_return=[(A,), (C,)])

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = [
                {
                    "event_id": A,
                    "occurred_at": "2025-08-21T06:52:34+03:00",
                    "user_id": 10,
                    "event_type": "login",
                    "properties": {"ip": "1.2.3.4"},
                },
                {
                    "event_id": B,
                    "occurred_at": "2025-08-21T06:52:35+03:00",
                    "user_id": 11,
                    "event_type": "logout",
                    "properties": {"k": 1},
                },
                {
                    "event_id": C,
                    "occurred_at": "2025-08-21T06:52:36+03:00",
                    "user_id": 12,
                    "event_type": "login",
                    "properties": {"k": 2},
                },
            ]
            r = await client.post("/events/", json=payload)

    assert r.status_code == 201, r.json()
    data = r.json()
    assert _norm_ids(data["inserted"]) == _norm_ids([A, C])
    assert _norm_ids(data["duplicates"]) == _norm_ids([B])
    assert fake_db.commits == 1
    assert calls["record_event"] == [{"name": "events_main"}]


@pytest.mark.asyncio
async def test_add_unique_events_empty_list_returns_empty_sets(make_app):
    """Empty input returns 201 with empty inserted/duplicates and no commit/metrics."""
    app, fake_db, calls = make_app(rows_to_return=[])

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post("/events/", json=[])

    assert r.status_code == 201, r.json()
    assert r.json() == {"inserted": [], "duplicates": []}
    assert fake_db.commits == 0
    assert calls["record_event"] == []


@pytest.mark.asyncio
async def test_rate_limiter_is_overridden_and_does_not_block(make_app):
    """Sanity check: request succeeds when rate limiter is neutralized."""
    app, _, _ = make_app(rows_to_return=[(X,)])

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = [{
                "event_id": X,
                "occurred_at": "2025-08-21T06:52:34+03:00",
                "user_id": 1,
                "event_type": "login",
                "properties": {},
            }]
            r = await client.post("/events/", json=payload)

    assert r.status_code == 201, r.json()
