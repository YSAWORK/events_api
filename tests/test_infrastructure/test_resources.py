# tests/test_infrastructure/test_resources.py

###### IMPORT TOOLS ######
# global imports
import asyncio
import importlib
import pytest
from starlette.requests import Request
from starlette.responses import PlainTextResponse


###### MARK ALL TESTS AS ASYNCIO ######
pytestmark = pytest.mark.asyncio

###### DUMMY CLASSES FOR MOCKING EXTERNAL DEPENDENCIES ######
class DummyRedis:
    def __init__(self):
        self.ping_called = False
        self.closed = False

    async def ping(self):
        self.ping_called = True
        return True

    async def aclose(self):
        self.closed = True


class DummyHTTPXClient:
    def __init__(self, *_, **__):
        self.closed = False

    async def aclose(self):
        self.closed = True


class DummyService:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.addr = None
        self.port = None

    async def start(self, addr: str, port: int):
        self.started = True
        self.addr = addr
        self.port = port

    async def stop(self):
        self.stopped = True


class DummyTask:
    def __init__(self):
        self.canceled = False

    def cancel(self):
        self.canceled = True


class DummyEngine:
    def __init__(self):
        self.disposed = False

    async def dispose(self):
        self.disposed = True


class DummySessionCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


####### FIXTURES ######
@pytest.fixture
def resources_mod(patched_main_env):
    import src.infrastructure.resources as res_mod
    res_mod = importlib.reload(res_mod)
    return res_mod


@pytest.fixture
def patch_external_libs(monkeypatch, resources_mod):
    """Patch external libraries used in resources module with dummy implementations."""
    import src.infrastructure.resources as res_mod
    dummy_redis = DummyRedis()
    monkeypatch.setattr(res_mod.aioredis, "from_url", lambda *a, **k: dummy_redis)
    monkeypatch.setattr(res_mod.httpx, "AsyncClient", DummyHTTPXClient)
    monkeypatch.setattr(res_mod, "Service", DummyService)
    async def noop_eps():
        return None
    monkeypatch.setattr(res_mod, "_update_events_per_second", noop_eps)
    class _DummyGauge:
        def set(self, *_args, **_kwargs):
            return None
    monkeypatch.setattr(res_mod, "events_per_second", _DummyGauge())
    dummy_task = DummyTask()
    def _fake_create_task(coro):
        try:
            coro.close()
        except Exception:
            pass
        return dummy_task
    monkeypatch.setattr(asyncio, "create_task", _fake_create_task)
    res_mod.resources.engine = DummyEngine()
    res_mod.resources.session_maker = lambda: DummySessionCtx()
    return {"dummy_redis": dummy_redis, "dummy_task": dummy_task}


###### TESTS FOR RESOURCES LIFECYCLE ######
async def test_start_initializes_once(resources_mod, patch_external_libs):
    """Test that starting resources initializes them only once."""
    res = resources_mod.resources
    assert res._started is False

    await res.start()
    assert res._started is True
    assert isinstance(res.http, DummyHTTPXClient)
    assert isinstance(res.metrics_service, DummyService)
    assert patch_external_libs["dummy_redis"].ping_called is True

    http_before = res.http
    metrics_before = res.metrics_service
    task_before = res.metrics_task
    await res.start()
    assert res.http is http_before
    assert res.metrics_service is metrics_before
    assert res.metrics_task is task_before


async def test_stop_cleans_up(resources_mod, patch_external_libs):
    """Test that stopping resources cleans them up properly."""
    res = resources_mod.resources
    await res.start()

    dummy_redis = patch_external_libs["dummy_redis"]
    dummy_task = patch_external_libs["dummy_task"]
    engine = res.engine

    await res.stop()

    assert res.http is None or getattr(res.http, "closed", True)
    assert dummy_redis.closed is True
    assert res.metrics_service is None or getattr(res.metrics_service, "stopped", True)
    assert dummy_task.canceled is True
    assert isinstance(engine, DummyEngine) and engine.disposed is True
    assert res._started is False


async def test_get_session_yields(resources_mod, patch_external_libs):
    """Test that get_session yields a session object."""
    res = resources_mod.resources

    async def consume():
        agen = res.get_session()
        session = None
        async for s in agen:
            session = s
            break
        return session

    s = await consume()
    assert s is not None


async def test_benchmark_token_middleware_allows_bypass(resources_mod, patched_main_env):
    """Test that benchmark token middleware sets is_benchmark flag correctly."""
    settings = resources_mod.get_settings()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/stats/dau",
        "headers": [(b"authorization", f"Bearer {settings.BENCHMARK_TOKEN}".encode())],
    }
    req = Request(scope)

    seen_state = {}

    async def call_next(r):
        seen_state["is_benchmark"] = getattr(r.state, "is_benchmark", False)
        return PlainTextResponse("OK", status_code=200)

    resp = await resources_mod.benchmark_token_middleware(req, call_next)
    assert resp.status_code == 200
    assert seen_state["is_benchmark"] is True


async def test_benchmark_token_middleware_ignores_wrong_path_or_token(resources_mod):
    """Test that benchmark token middleware does not set is_benchmark flag for wrong paths or tokens."""
    scope1 = {
        "type": "http",
        "method": "GET",
        "path": "/health",
        "headers": [(b"authorization", b"Bearer TEST_TOKEN_VALUE")],
    }
    req1 = Request(scope1)

    async def call_next1(r):
        assert not hasattr(r.state, "is_benchmark")
        return PlainTextResponse("OK", status_code=200)

    resp1 = await resources_mod.benchmark_token_middleware(req1, call_next1)
    assert resp1.status_code == 200

    scope2 = {
        "type": "http",
        "method": "GET",
        "path": "/stats/dau",
        "headers": [(b"authorization", b"Bearer WRONG")],
    }
    req2 = Request(scope2)

    seen = {}

    async def call_next2(r):
        seen["has_flag"] = hasattr(r.state, "is_benchmark")
        return PlainTextResponse("OK", status_code=200)

    resp2 = await resources_mod.benchmark_token_middleware(req2, call_next2)
    assert resp2.status_code == 200
    assert seen["has_flag"] is False
