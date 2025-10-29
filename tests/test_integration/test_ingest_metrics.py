# tests/test_integration/test_ingest_metrics.py

###### IMPORT TOOLS ######
# global imports
import os
import uuid
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient, ASGITransport

###### MARK ALL TESTS AS ASYNCIO ######
pytestmark = pytest.mark.asyncio

###### HELPERS ######
def _resolve_app(factory):
    maybe = factory()
    return maybe[0] if isinstance(maybe, tuple) else maybe


def _patch_fastapi_limiter_globals():
    try:
        from fastapi_limiter import FastAPILimiter

        class _DummyRedis:
            async def eval(self, *a, **k): return 1
            async def ttl(self, *a, **k): return 1
            async def get(self, *a, **k): return None
            async def set(self, *a, **k): return True

        FastAPILimiter.redis = _DummyRedis()
    except Exception:
        pass


def _patch_jose_jwt_decode():
    """Return a fixed payload for any JWT decode attempt."""
    try:
        import jose.jwt as _jwt

        def _fake_decode(token, *_, **__):
            return {"sub": "1", "user_id": 1, "type": "access", "scope": "stats:read", "exp": 4102444800}

        def _fake_get_unverified_header(token):
            return {"alg": "HS256", "typ": "JWT"}

        _jwt.decode = _fake_decode
        _jwt.get_unverified_header = _fake_get_unverified_header
    except Exception:
        pass


def _override_rate_limiters(app):
    """This neutralizes all RateLimiter dependencies in the FastAPI app."""
    try:
        from fastapi_limiter.depends import RateLimiter  # noqa
    except Exception:
        return

    for route in getattr(app, "routes", []):
        dep = getattr(route, "dependant", None)
        if not dep:
            continue
        for d in (dep.dependencies or []):
            call = getattr(d, "call", None)
            if call and getattr(call, "__class__", None).__name__ == "RateLimiter":
                app.dependency_overrides[call] = (lambda: None)


def _walk_dependants(root):
    """The depth-first traversal of FastAPI Dependant tree."""
    stack = [root]
    out = []
    while stack:
        dep = stack.pop()
        if not dep:
            continue
        out.append(dep)
        for ch in (dep.dependencies or []):
            stack.append(ch)
    return out


def _override_auth_everywhere(app):
    """This neutralizes all authentication dependencies in the FastAPI app."""
    dummy_user = SimpleNamespace(
        id=1, email="test@example.com", is_active=True, is_superuser=True, is_staff=True
    )
    name_patterns = ("get_current_", "current_user", "require_", "auth")
    module_patterns = ("src.user_auth", "src.endpoint_stats", "src.auth", "user_auth", "auth")

    for route in getattr(app, "routes", []):
        root = getattr(route, "dependant", None)
        if not root:
            continue
        for dep in _walk_dependants(root):
            call = getattr(dep, "call", None)
            if not call:
                continue
            fname = getattr(call, "__name__", "")
            fmod = getattr(call, "__module__", "") or ""
            is_auth_name = any(p in fname for p in name_patterns)
            is_auth_mod = any(p in fmod for p in module_patterns)
            if is_auth_name or is_auth_mod:
                app.dependency_overrides[call] = (lambda: dummy_user)

            cls = getattr(call, "__class__", None)
            if cls and (cls.__name__ in ("OAuth2PasswordBearer", "HTTPBearer") or "fastapi.security" in fmod):
                app.dependency_overrides[call] = (lambda: "TEST")


def _find_route(app, *, method: str, endswith: str | None = None, contains: list[str] | None = None) -> str:
    method = method.upper()
    routes = []
    for r in getattr(app, "routes", []):
        methods = getattr(r, "methods", set()) or set()
        if method not in methods:
            continue
        path = getattr(r, "path", None) or getattr(r, "path_format", None)
        if isinstance(path, str):
            routes.append(path)

    if endswith:
        for p in routes:
            if p.endswith(endswith):
                return p
    if contains:
        for p in routes:
            low = p.lower()
            if all(s in low for s in contains):
                return p

    raise AssertionError(
        f"Could not find route method={method} endswith={endswith} contains={contains}. "
        f"Available {method} routes: {sorted(routes)}"
    )


# ---------- The test ----------
@pytest.mark.asyncio
async def test_ingest_then_query_dau(patched_main_env, fresh_app_factory):
    """Test ingesting events and querying Daily Active Users (DAU) over a date range."""
    _patch_jose_jwt_decode()

    app = _resolve_app(fresh_app_factory)
    _patch_fastapi_limiter_globals()
    _override_rate_limiters(app)
    _override_auth_everywhere(app)

    headers = {
        "X-Benchmark-Token": os.getenv("BENCHMARK_TOKEN", "TEST_TOKEN_VALUE"),
        "Authorization": "Bearer TEST",
    }

    ingest_path = _find_route(app, method="POST", endswith="/events/", contains=["events"])
    stats_path  = _find_route(app, method="GET",  endswith="/stats/dau", contains=["stats", "dau"])

    day0 = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    day1 = day0 + timedelta(days=1)

    from_date = day0.date().isoformat()
    to_date_exclusive = (day1.date() + timedelta(days=1)).isoformat()

    events = [
        {"event_id": str(uuid.uuid4()), "occurred_at": day0.isoformat(), "user_id": 101, "event_type": "login",    "properties": {"country": "UA"}},
        {"event_id": str(uuid.uuid4()), "occurred_at": day0.isoformat(), "user_id": 202, "event_type": "purchase", "properties": {"amount": 7}},
        {"event_id": str(uuid.uuid4()), "occurred_at": day1.isoformat(), "user_id": 101, "event_type": "app_open", "properties": {"platform": "web"}},
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        # 1) Ingest
        ir = await client.post(ingest_path, json=events)
        assert ir.status_code in (200, 201), f"Ingest failed at {ingest_path}: {ir.status_code} {ir.text}"

        # 2) Stats
        params = {"from": from_date, "to": to_date_exclusive}
        sr = await client.get(stats_path, params=params)
        if sr.status_code in (400, 422):
            params = {"start": from_date, "end": to_date_exclusive}
            sr = await client.get(stats_path, params=params)
        assert sr.status_code == 200, f"DAU query failed at {stats_path}: {sr.status_code} {sr.text}"
        data = sr.json()

    assert isinstance(data, dict), f"Unexpected DAU payload: {type(data)} :: {data}"
    d0, d1 = day0.date().isoformat(), day1.date().isoformat()
    assert data.get(d0, 0) >= 2, f"Expected >=2 DAU for {d0}, got {data.get(d0)}"
    assert data.get(d1, 0) >= 1, f"Expected >=1 DAU for {d1}, got {data.get(d1)}"
