# ./tests/test_user_auth/test_routers.py

###### IMPORT TOOLS ######
# global imports
import sys
import types
import importlib
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient


###### HELPER FUNCTION ######
def _build_app_with_patches(monkeypatch, scenario=None):
    """Create a FastAPI app with the auth router, patching infra and deps for the given scenario."""
    for m in [
        "src.user_auth.routers",
        "src.infrastructure.resources",
        "fastapi_limiter.depends",
        "src.security.token_cache",
        "src.security.jwt_service",
        "src.user_auth.utils",
        "src.data_base.crud",
        "src.data_base.models",
    ]:
        sys.modules.pop(m, None)

    dep_mod = importlib.import_module("fastapi_limiter.depends")

    class _NoOpRateLimiter:
        def __init__(self, *args, **kwargs):
            pass
        def __call__(self):
            async def _dep():
                return None
            return _dep

    monkeypatch.setattr(dep_mod, "RateLimiter", _NoOpRateLimiter, raising=False)
    res_mod = types.ModuleType("src.infrastructure.resources")

    class _StubSession:
        """Minimal async session stub with get/commit/rollback."""
        def __init__(self, user_obj=None):
            self._user_obj = user_obj
            self.committed = False
            self.rolled_back = False

        async def get(self, model, pk: int):
            return self._user_obj

        async def commit(self):
            self.committed = True

        async def rollback(self):
            self.rolled_back = True

    class _StubResources:
        def __init__(self):
            self.redis = object()

        async def get_session(self):
            session = _StubSession(user_obj=getattr(_ctx, "db_user_for_get", None))
            try:
                yield session
            finally:
                pass

    async def _dummy_benchmark_token_middleware(request, call_next):
        """No-op middleware to replace actual benchmarking middleware."""
        return await call_next(request)

    res_mod.resources = _StubResources()
    res_mod.benchmark_token_middleware = _dummy_benchmark_token_middleware
    sys.modules["src.infrastructure.resources"] = res_mod

    class _Ctx: ...
    _ctx = _Ctx()
    _ctx.user_for_email = None
    _ctx.verify_password_result = True
    _ctx.issue_tokens = {"access_token": "acc", "refresh_token": "ref", "token_type": "bearer"}
    _ctx.decode_payload = {
        "jti": "jti-1",
        "sub": 1,
        "exp": int((datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp()),
        "type": "refresh",
    }
    _ctx.token_revoked = False
    _ctx.token_present_in_cache = True
    _ctx.db_user_for_get = None
    _ctx.get_user_duplicate = False
    _ctx.create_user_obj = None
    _ctx.raise_integrity_on_commit = False

    crud_mod = types.ModuleType("src.data_base.crud")

    async def _get_user_by_email(db, email: str):
        """Return the preset user for email from context."""
        return _ctx.user_for_email

    class _User:
        def __init__(self, id, email, hashed_password="hash"):
            self.id = id
            self.email = email
            self.hashed_password = hashed_password

    async def _create_user(db, payload):
        """Create and return a user based on context settings."""
        return _ctx.create_user_obj or _User(10, str(payload.email), "hashed!")

    async def _get_current_user():
        """Return the preset current user from context."""
        return _ctx.current_user or _User(1, "me@example.com", "hashed_current")

    crud_mod.get_user_by_email = _get_user_by_email
    crud_mod.create_user = _create_user
    crud_mod.get_current_user = _get_current_user
    sys.modules["src.data_base.crud"] = crud_mod
    models_mod = types.ModuleType("src.data_base.models")
    models_mod.User = _User
    sys.modules["src.data_base.models"] = models_mod
    utils_mod = types.ModuleType("src.user_auth.utils")

    def _verify_password(plain, hashed):
        """Return the preset password verification result from context."""
        return _ctx.verify_password_result

    def _get_password_hash(pwd):
        """Return a dummy hashed password."""
        return "hashed_new"

    def _check_authorization(user_id, current_user_id):
        """Raise if user_id does not match current_user_id."""
        if user_id != current_user_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="You can only access your own data.")

    utils_mod.verify_password = _verify_password
    utils_mod.get_password_hash = _get_password_hash
    utils_mod.check_authorization = _check_authorization
    sys.modules["src.user_auth.utils"] = utils_mod
    tok_mod = types.ModuleType("src.security.token_cache")

    class _TokenCache:
        def __init__(self, redis): ...
        async def is_revoked(self, jti): return _ctx.token_revoked
        async def get_refresh(self, jti): return _ctx.token_present_in_cache
        async def revoke(self, jti, exp): _ctx.revoked = True
        async def delete_refresh(self, jti): _ctx.deleted = True
        async def revoke_all_user_refresh(self, sub): _ctx.revoked_all = True

    async def _issue_tokens_for_user(user_id: int, access: bool, refresh: bool):
        """ Issue tokens based on context settings."""
        return _ctx.issue_tokens

    tok_mod.TokenCache = _TokenCache
    tok_mod.issue_tokens_for_user = _issue_tokens_for_user
    sys.modules["src.security.token_cache"] = tok_mod
    jwt_mod = types.ModuleType("src.security.jwt_service")

    def _decode_token(token: str, expected_type: str = "refresh"):
        """Return the preset decoded payload from context."""
        return _ctx.decode_payload

    jwt_mod.decode_token = _decode_token
    sys.modules["src.security.jwt_service"] = jwt_mod
    metrics_mod = types.ModuleType("src.infrastructure.metrics")
    def _record_event(event): ...
    metrics_mod.record_event = _record_event
    sys.modules["src.infrastructure.metrics"] = metrics_mod
    auth_mod = importlib.import_module("src.user_auth.routers")
    router = auth_mod.router
    app = FastAPI()
    app.include_router(router)
    app._ctx = _ctx
    return app


###### TESTS ######
def test_register_success(monkeypatch):
    """Register returns 201 and user payload when email is free."""
    app = _build_app_with_patches(monkeypatch)
    app._ctx.user_for_email = None
    app._ctx.create_user_obj = type("U", (), {
        "id": 5,
        "email": "new@ex.com",
        "hashed_password": "h",
        "created_at": datetime.now(timezone.utc),
    })()

    client = TestClient(app)
    r = client.post("/auth/register", json={
        "email": "new@ex.com",
        "password": "ValidP!ss1",
        "password_confirm": "ValidP!ss1",
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["id"] == 5
    assert data["email"] == "new@ex.com"


def test_register_conflict(monkeypatch):
    """Register returns 409 when email already exists."""
    app = _build_app_with_patches(monkeypatch)
    app._ctx.user_for_email = object()
    client = TestClient(app)
    r = client.post("/auth/register", json={
        "email": "dup@ex.com",
        "password": "ValidP!ss1",
        "password_confirm": "ValidP!ss1",
    })
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]


def test_login_success(monkeypatch):
    """Login returns token pair on valid credentials."""
    app = _build_app_with_patches(monkeypatch)
    app._ctx.user_for_email = type("U", (), {"id": 7, "email": "u@ex.com", "hashed_password": "h"})()
    app._ctx.verify_password_result = True
    app._ctx.issue_tokens = {"access_token": "A", "refresh_token": "R", "token_type": "bearer"}
    client = TestClient(app)
    r = client.post("/auth/login", json={"email": "u@ex.com", "password": "GoodPass1!"})
    assert r.status_code == 200
    body = r.json()
    assert body["access"] == "A"
    assert body["refresh"] == "R"
    assert body["token_type"] == "bearer"


def test_login_wrong_password(monkeypatch):
    """Login returns 401 for wrong email or password."""
    app = _build_app_with_patches(monkeypatch)
    app._ctx.user_for_email = type("U", (), {"id": 7, "email": "u@ex.com", "hashed_password": "h"})()
    app._ctx.verify_password_result = False  # simulate mismatch
    client = TestClient(app)
    r = client.post("/auth/login", json={"email": "u@ex.com", "password": "WrongPass1!"})
    assert r.status_code == 401, r.text
    assert "Wrong password or email" in r.json()["detail"]



def test_oauth2_token_success(monkeypatch):
    """OAuth2 /auth/token issues access token for valid credentials."""
    app = _build_app_with_patches(monkeypatch)
    app._ctx.user_for_email = type("U", (), {"id": 3, "email": "u@ex.com", "hashed_password": "h"})()
    app._ctx.verify_password_result = True
    app._ctx.issue_tokens = {"access_token": "ONLY-ACCESS", "token_type": "bearer"}
    client = TestClient(app)
    r = client.post("/auth/token", data={"username": "u@ex.com", "password": "good"})
    assert r.status_code == 200
    assert r.json()["access_token"] == "ONLY-ACCESS"
    assert r.json()["token_type"] == "bearer"


def test_refresh_success(monkeypatch):
    """Refresh returns new token pair and revokes old refresh."""
    app = _build_app_with_patches(monkeypatch)
    app._ctx.token_revoked = False
    app._ctx.token_present_in_cache = True
    app._ctx.issue_tokens = {"access_token": "NEW-A", "refresh_token": "NEW-R", "token_type": "bearer"}
    client = TestClient(app)
    r = client.post("/auth/1/refresh", json={"refresh": "refresh-token"})
    assert r.status_code == 200
    body = r.json()
    assert body["access"] == "NEW-A"
    assert body["refresh"] == "NEW-R"


def test_refresh_revoked(monkeypatch):
    """Refresh fails with 401 when refresh token is revoked."""
    app = _build_app_with_patches(monkeypatch)
    app._ctx.token_revoked = True
    app._ctx.token_present_in_cache = True
    client = TestClient(app)
    r = client.post("/auth/1/refresh", json={"refresh": "refresh-token"})
    assert r.status_code == 401
    assert "revoked" in r.json()["detail"]


def test_logout_success(monkeypatch):
    """Logout revokes and deletes refresh token."""
    app = _build_app_with_patches(monkeypatch)
    app._ctx.current_user = type("U", (), {"id": 5, "email": "me@ex.com"})()
    app._ctx.decode_payload = {
        "type": "refresh",
        "sub": 5,
        "jti": "jti-x",
        "exp": int((datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    app._ctx.token_revoked = False
    app._ctx.token_present_in_cache = True
    client = TestClient(app)
    r = client.post("/auth/5/logout", json={"refresh": "rtok"})
    assert r.status_code == 204


def test_logout_malformed_refresh(monkeypatch):
    """Logout fails when refresh token payload is missing fields."""
    app = _build_app_with_patches(monkeypatch)
    app._ctx.current_user = type("U", (), {"id": 5, "email": "me@ex.com"})()
    app._ctx.decode_payload = {"type": "refresh"}
    client = TestClient(app)
    r = client.post("/auth/5/logout", json={"refresh": "rtok"})
    assert r.status_code == 400
    assert "Malformed" in r.json()["detail"]


def test_change_password_success(monkeypatch):
    """Change password commits and revokes all refresh tokens."""
    app = _build_app_with_patches(monkeypatch)
    u = type("U", (), {"id": 9, "email": "me@ex.com", "hashed_password": "h"})()
    app._ctx.current_user = u
    app._ctx.db_user_for_get = u
    app._ctx.verify_password_result = True
    client = TestClient(app)
    r = client.post(
        "/auth/9/change-password",
        json={
            "current_password": "OldP!ssw0rd1",
            "new_password": "NewP!ssw0rd1",
            "new_password_confirm": "NewP!ssw0rd1",
        },
    )
    assert r.status_code == 204


def test_change_password_wrong_current(monkeypatch):
    """Change password fails with 401 when current password is incorrect."""
    app = _build_app_with_patches(monkeypatch)
    u = type("U", (), {"id": 9, "email": "me@ex.com", "hashed_password": "h"})()
    app._ctx.current_user = u
    app._ctx.db_user_for_get = u
    app._ctx.verify_password_result = False
    client = TestClient(app)
    request = client.post(
        "/auth/9/change-password",
        json={
            "current_password": "WrongPass1!",
            "new_password": "NewP!ssw0rd1",
            "new_password_confirm": "NewP!ssw0rd1",
        },
    )
    assert request.status_code == 401, request.text
    assert "Current password is incorrect" in request.json()["detail"]
