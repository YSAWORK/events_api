# tests/test_src/conftest.py
import sys
import importlib
import pytest
from fastapi_limiter import FastAPILimiter


@pytest.fixture(scope="session")
def patched_main_env(tmp_path_factory):
    """
    Session-scoped: вимикає реальні ресурси (БД/Redis), готує STATIC_DIR,
    патчить FastAPILimiter та resources. ЖОДНОГО function-scoped monkeypatch тут.
    """
    mp = pytest.MonkeyPatch()            # <- НЕ фікстура, а клас
    mp.setenv("APP_ENV", "test")
    mp.setenv("UNIT_TESTS_ONLY", "1")
    mp.setenv("DISABLE_DB_FOR_TESTS", "1")
    mp.setenv("BENCHMARK_TOKEN", "TEST_TOKEN_VALUE")
    mp.setenv("API_PREFIX", "/api")
    mp.setenv("DEBUG", "0")

    static_dir = tmp_path_factory.mktemp("static")
    mp.setenv("STATIC_DIR", str(static_dir))

    # no-op FastAPILimiter.init
    async def _noop_init(*args, **kwargs):
        return None
    mp.setattr(FastAPILimiter, "init", _noop_init, raising=False)

    # stub resources
    res_mod = importlib.import_module("src.infrastructure.resources")

    class _StubResources:
        def __init__(self):
            self.redis = object()
            self.started = False
            self.stopped = False
        async def start(self):
            self.started = True
        async def stop(self):
            self.stopped = True

    async def _stub_benchmark_token_middleware(request, call_next):
        return await call_next(request)

    stub = _StubResources()
    mp.setattr(res_mod, "resources", stub, raising=False)
    mp.setattr(res_mod, "benchmark_token_middleware", _stub_benchmark_token_middleware, raising=False)

    try:
        yield stub
    finally:
        mp.undo()  # важливо повернути середовище у норму


@pytest.fixture
def fresh_app_factory(patched_main_env):
    """
    Function-scoped фабрика: очищає кеш імпорту та повертає (app, resources).
    Можна попередньо виставити env через function-scoped `monkeypatch` у тесті.
    """
    def _factory():
        for m in ["src.main", "src.config", "src.routers", "src.infrastructure.resources"]:
            sys.modules.pop(m, None)
        from src.main import app
        from src.infrastructure.resources import resources
        return app, resources
    return _factory


