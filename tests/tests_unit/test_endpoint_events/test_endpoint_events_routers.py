# ./tests/

###### IMPORT TOOLS ######
# global import
import pytest
from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager

# local import
from src.endpoint_events import routers as events_routers


####### FAKES & HELPERS ########
class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    class _Scalars:
        def __init__(self, rows):
            self._vals = [r[0] for r in rows]
        def all(self):
            return self._vals

    def scalars(self):
        return self._Scalars(self._rows)

    class _Mappings:
        def __init__(self, rows):
            self._maps = [{"event_id": r[0]} for r in rows]
        def all(self):
            return self._maps

    def mappings(self):
        return self._Mappings(self._rows)


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


###### FIXTURES #######
@pytest.fixture
def make_app(monkeypatch):
    """
    Build a minimal FastAPI app with the router under test and:
      - override events_routers.resources.get_session -> FakeAsyncSession (IMPORTANT)
      - override record_event -> spy collector
      - neutralize all route-level Depends(...) (e.g., RateLimiter) with a NO-ARG no-op
      - override the exact callable objects held in FastAPI dependency graph
    """
    from fastapi import FastAPI

    def _noop_dep():
        return None

    def _factory(rows_to_return):
        app = FastAPI()
        calls = {"record_event": []}
        monkeypatch.setattr(
            events_routers, "record_event",
            lambda payload: calls["record_event"].append(payload),
            raising=True,
        )

        fake_db = FakeAsyncSession(rows_to_return)
        monkeypatch.setattr(
            events_routers.resources, "get_session",
            lambda: fake_db,
            raising=True,
        )

        app.include_router(events_routers.router)
        for route in app.router.routes:
            for dep in getattr(route, "dependencies", []) or []:
                if getattr(dep, "dependency", None):
                    app.dependency_overrides[dep.dependency] = _noop_dep

        for route in app.router.routes:
            dependant = getattr(route, "dependant", None)
            if not dependant:
                continue
            for dep in dependant.dependencies or []:
                call = getattr(dep, "call", None)
                name = getattr(call, "__name__", "")
                qual = getattr(call, "__qualname__", "")
                if call and (call is events_routers.resources.get_session or
                             name == "get_session" or
                             qual.endswith("get_session")):
                    app.dependency_overrides[call] = lambda: fake_db

        return app, fake_db, calls

    return _factory


# Valid UUIDs for payloads
A = "11111111-1111-1111-1111-111111111111"
B = "22222222-2222-2222-2222-222222222222"
C = "33333333-3333-3333-3333-333333333333"
X = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


# ---------- Tests ----------


###### TESTS ######
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
