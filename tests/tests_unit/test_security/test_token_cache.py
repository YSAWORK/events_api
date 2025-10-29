# ./tests/test_security/test_token_cache.py

###### IMPORT TOOLS ######
# global imports
import sys
import types
import pytest
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone


###### FAKE REDIS (ASYNC) ######
class FakeRedis:
    """Minimal async Redis stub with TTL and set semantics used by TokenCache."""
    def __init__(self):
        self._kv: dict[str, tuple[str, datetime | None]] = {}
        self._sets: dict[str, set[str]] = {}

    async def set(self, key: str, value: str, ex: int | None = None):
        expires_at = None
        if ex is not None:
            expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=ex)
        self._kv[key] = (value, expires_at)

    async def get(self, key: str):
        v = self._kv.get(key)
        if not v:
            return None
        value, exp = v
        if exp and exp <= datetime.now(tz=timezone.utc):
            self._kv.pop(key, None)
            return None
        return value

    async def delete(self, key: str):
        self._kv.pop(key, None)

    async def exists(self, key: str) -> int:
        v = await self.get(key)
        return 1 if v is not None else 0

    async def ttl(self, key: str) -> int:
        v = self._kv.get(key)
        if not v:
            return -2
        _, exp = v
        if exp is None:
            return -1
        delta = int((exp - datetime.now(tz=timezone.utc)).total_seconds())
        return max(delta, 0)

    async def sadd(self, key: str, member: str):
        self._sets.setdefault(key, set()).add(member)

    async def srem(self, key: str, member: str):
        if key in self._sets:
            self._sets[key].discard(member)
            if not self._sets[key]:
                self._sets.pop(key, None)

    async def smembers(self, key: str):
        return set(self._sets.get(key, set()))


###### FIXTURES ######
@pytest.fixture
def patched_token_cache_env(monkeypatch):
    """
    Patch resources.redis -> FakeRedis.
    Import token_cache and THEN force-attach a fake jwt_service to the module object
    (so even if src.security.__init__ re-exports the real one, our stub wins).
    """
    for m in [
        "src.user_auth.token_cache",
        "src.security.token_cache",
        "src.infrastructure.resources",
        "src.security.jwt_service",
        "src.security",
        "src.config",
    ]:
        sys.modules.pop(m, None)

    import src.config as cfg
    cfg.get_settings.cache_clear()
    redis = FakeRedis()
    res_mod = types.ModuleType("src.infrastructure.resources")
    res_mod.resources = SimpleNamespace(redis=redis)
    sys.modules["src.infrastructure.resources"] = res_mod
    calls = {"access": [], "refresh": []}
    jwt_stub = types.ModuleType("jwt_service_stub")

    def make_access_token(*, sub: str, jti: str, exp, typ: str):
        calls["access"].append({"sub": sub, "jti": jti, "exp": exp, "typ": typ})
        return "FAKE.ACCESS.JWT"

    def make_refresh_token(*, sub: str, jti: str, exp, typ: str):
        calls["refresh"].append({"sub": sub, "jti": jti, "exp": exp, "typ": typ})
        return "FAKE.REFRESH.JWT"

    jwt_stub.make_access_token = make_access_token
    jwt_stub.make_refresh_token = make_refresh_token


    import src.security.token_cache as tc
    monkeypatch.setattr(tc, "jwt_service", jwt_stub, raising=False)

    return SimpleNamespace(tc=tc, calls=calls, redis=redis)



###### TESTS ######
@pytest.mark.asyncio
async def test_register_refresh_and_get_and_ttl(patched_token_cache_env):
    """Register a refresh token then retrieve it and verify TTL is positive."""
    env = patched_token_cache_env
    cache = env.tc.TokenCache(env.redis)

    user_id = 42
    jti = "refresh-jti-1"
    payload = {"sub": user_id}
    exp = datetime.now(tz=timezone.utc) + timedelta(minutes=30)

    await cache.register_refresh(user_id, jti, payload, exp)
    got = await cache.get_refresh(jti)
    ttl = await cache.ttl_of_refresh(jti)

    assert got == payload
    assert ttl > 0


@pytest.mark.asyncio
async def test_revoke_refresh_marks_revoked_and_deletes(patched_token_cache_env):
    """Revoke refresh moves it to 'revoked' key and deletes original refresh value."""
    env = patched_token_cache_env
    cache = env.tc.TokenCache(env.redis)

    user_id = 1
    jti = "rjti"
    exp = datetime.now(tz=timezone.utc) + timedelta(minutes=10)

    await cache.register_refresh(user_id, jti, {"sub": user_id}, exp)
    ok = await cache.revoke_refresh(jti)

    assert ok is True
    assert await cache.get_refresh(jti) is None
    assert await cache.is_revoked(jti) is True


@pytest.mark.asyncio
async def test_revoke_all_user_refresh_revokes_all_and_clears_set(patched_token_cache_env):
    """Revoke all refresh tokens for a user and ensure the sessions set is cleared."""
    env = patched_token_cache_env
    cache = env.tc.TokenCache(env.redis)

    user_id = 77
    exp = datetime.now(tz=timezone.utc) + timedelta(minutes=5)

    await cache.register_refresh(user_id, "jti-1", {"sub": user_id}, exp)
    await cache.register_refresh(user_id, "jti-2", {"sub": user_id}, exp)

    count = await cache.revoke_all_user_refresh(user_id)
    assert count == 2
    assert await cache.get_refresh("jti-1") is None
    assert await cache.get_refresh("jti-2") is None

    # Internal set should be empty
    key_set = cache._key_user_sessions(user_id)
    members = await env.redis.smembers(key_set)
    assert not members


@pytest.mark.asyncio
async def test_store_and_get_access_and_refresh(patched_token_cache_env):
    """Store access/refresh payloads and get them back until they expire."""
    env = patched_token_cache_env
    cache = env.tc.TokenCache(env.redis)

    jta = "a-1"
    jtr = "r-1"
    exp = datetime.now(tz=timezone.utc) + timedelta(seconds=60)

    await cache.store_access(jta, {"sub": 10}, exp)
    await cache.store_refresh(jtr, {"sub": 11}, exp)

    get_a = await cache.get_access(jta)
    get_r = await cache.get_refresh(jtr)

    assert get_a == {"sub": 10}
    assert get_r == {"sub": 11}


@pytest.mark.asyncio
async def test_revoke_flag_and_delete_methods(patched_token_cache_env):
    """Explicit revoke() sets revoked flag; delete_* remove entries."""
    env = patched_token_cache_env
    cache = env.tc.TokenCache(env.redis)

    jta = "A"
    jtr = "R"
    exp = datetime.now(tz=timezone.utc) + timedelta(minutes=1)

    await cache.store_access(jta, {"x": 1}, exp)
    await cache.store_refresh(jtr, {"y": 2}, exp)

    await cache.revoke(jtr, exp)
    await cache.delete_access(jta)
    await cache.delete_refresh(jtr)

    assert await cache.get_access(jta) is None
    assert await cache.get_refresh(jtr) is None
    assert await cache.is_revoked(jtr) is True


@pytest.mark.asyncio
async def test_issue_tokens_for_user_access_only_stores_access_and_expires_in(patched_token_cache_env):
    """Issue only access token: payload stored; expires_in ~ 15 minutes."""
    env = patched_token_cache_env

    res = await env.tc.issue_tokens_for_user(5, access=True, refresh=False)

    assert res["access_token"] == "FAKE.ACCESS.JWT"
    assert res["refresh_token"] is None
    assert res["token_type"] == "bearer"
    assert isinstance(res["expires_in"], int) and 1 <= res["expires_in"] <= 15 * 60
    assert env.calls["access"], "make_access_token was not called"
    jti = env.calls["access"][0]["jti"]
    stored = await env.tc.TokenCache(env.redis).get_access(jti)
    assert stored == {"sub": 5}


@pytest.mark.asyncio
async def test_issue_tokens_for_user_refresh_only_stores_refresh(patched_token_cache_env):
    """Issue only refresh token: payload stored; expires_in is None."""
    env = patched_token_cache_env

    res = await env.tc.issue_tokens_for_user(9, access=False, refresh=True)

    assert res["access_token"] is None
    assert res["refresh_token"] == "FAKE.REFRESH.JWT"
    assert res["expires_in"] is None

    assert env.calls["refresh"], "make_refresh_token was not called"
    jti = env.calls["refresh"][0]["jti"]
    stored = await env.tc.TokenCache(env.redis).get_refresh(jti)
    assert stored == {"sub": 9}


@pytest.mark.asyncio
async def test_issue_tokens_for_user_both_tokens(patched_token_cache_env):
    """Issue both tokens: both payloads stored and fields present."""
    env = patched_token_cache_env

    res = await env.tc.issue_tokens_for_user(11, access=True, refresh=True)

    assert res["access_token"] == "FAKE.ACCESS.JWT"
    assert res["refresh_token"] == "FAKE.REFRESH.JWT"
    assert res["token_type"] == "bearer"
    assert isinstance(res["expires_in"], int) and res["expires_in"] > 0

    assert env.calls["access"], "make_access_token was not called"
    jti_a = env.calls["access"][0]["jti"]
    assert env.calls["refresh"], "make_refresh_token was not called"
    jti_r = env.calls["refresh"][0]["jti"]

    cache = env.tc.TokenCache(env.redis)
    assert await cache.get_access(jti_a) == {"sub": 11}
    assert await cache.get_refresh(jti_r) == {"sub": 11}
