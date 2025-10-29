# tests/test_infrastructure/test_cache_setup.py
# This file contains tests for the cache setup in the infrastructure module.


####### IMPORT TOOLS #######
# global imports
import types
import copy
import pytest
from aiocache import caches

# local imports
from src.infrastructure.cache import setup_aiocache


# Fixtures
@pytest.fixture(autouse=True)
def _isolate_aiocache_config():
    """Ensure aiocache config is reset before and after each test."""
    old_cfg = copy.deepcopy(caches.get_config())
    try:
        yield
    finally:
        if old_cfg:
            caches.set_config(old_cfg)
        else:
            caches.set_config({})


# Mock get_settings to return controlled REDIS_URL
@pytest.fixture
def fake_settings(monkeypatch):
    """Provide fake settings with a test Redis URL."""
    class S(types.SimpleNamespace):
        pass

    s = S()
    s.REDIS_URL = "redis://localhost:6379/1"

    def fake_get_settings():
        return s

    monkeypatch.setattr("src.infrastructure.cache.get_settings", fake_get_settings)
    return s


####### TESTS FOR CACHE SETUP #######
# Happy path: setup_aiocache sets expected config
def test_setup_aiocache_sets_expected_config(fake_settings):
    """Test that setup_aiocache configures aiocache with Redis and JSON serializer."""
    setup_aiocache()
    cfg = caches.get_config()
    assert "default" in cfg
    default = cfg["default"]
    assert default["cache"] == "aiocache.RedisCache"
    assert default["endpoint"] == fake_settings.REDIS_URL
    assert "serializer" in default
    assert default["serializer"]["class"] == "aiocache.serializers.JsonSerializer"
    assert default["namespace"] == "rq"
    assert default["timeout"] == 1
    cache = caches.get("default")
    assert getattr(cache, "namespace", None) == "rq"
    assert getattr(cache, "timeout", None) == 1
    assert cache.serializer.__class__.__name__ == "JsonSerializer"


# Idempotency: multiple calls yield same config
def test_setup_aiocache_is_idempotent(fake_settings):
    """Test that multiple calls to setup_aiocache yield the same configuration."""
    setup_aiocache()
    first_cfg = copy.deepcopy(caches.get_config())
    setup_aiocache()
    second_cfg = caches.get_config()
    assert first_cfg == second_cfg
