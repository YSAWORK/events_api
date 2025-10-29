# ./tests/test_data_base/test_crud.py

import asyncio
import types
from types import SimpleNamespace
import pytest
from fastapi import HTTPException, Request
from jose import JWTError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import src.data_base.crud as crud


# ----------------- Fakes & helpers -----------------

class FakeResult:
    def __init__(self, obj):
        self._obj = obj
    def scalar_one_or_none(self):
        return self._obj


class FakeAsyncSession:
    """Minimal AsyncSession stub to observe calls and control returns."""
    def __init__(self):
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.refreshed = []
        # For controlling execute() result
        self._next_execute_result = None

    def set_execute_result(self, obj):
        self._next_execute_result = obj

    async def execute(self, *args, **kwargs):
        return FakeResult(self._next_execute_result)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)


@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    """Stub get_settings() for secrets and JWT config."""
    monkeypatch.setattr(
        crud,
        "get_settings",
        lambda: SimpleNamespace(
            ACCESS_SECRET="test-access",
            JWT_ALG="HS256",
            JWT_AUDIENCE="test-aud",
            JWT_ISSUER="test-iss",
        ),
    )


@pytest.fixture
def stub_select(monkeypatch):
    """Make crud.select(...) return a chainable dummy that ignores args."""
    class _FakeSelect:
        def where(self, *args, **kwargs):
            return self
        def limit(self, *args, **kwargs):
            return self
    monkeypatch.setattr(crud, "select", lambda *a, **k: _FakeSelect())


@pytest.fixture
def fake_user_class(monkeypatch):
    """Replace ORM User with a lightweight class that also exposes class-level columns."""
    class FakeUser:
        # mimic mapped column attributes used in queries
        email = "EMAIL_COL"
        id = "ID_COL"

        def __init__(self, email=None, hashed_password=None, id=None):
            self.email = email
            self.hashed_password = hashed_password
            self.id = id

    monkeypatch.setattr(crud, "User", FakeUser)
    return FakeUser


@pytest.fixture
def fake_session():
    return FakeAsyncSession()


# ----------------- get_user_by_email -----------------

@pytest.mark.asyncio
async def test_get_user_by_email_found(monkeypatch, fake_session, fake_user_class, stub_select):
    user = fake_user_class(email="u@example.com", hashed_password="x", id=1)
    fake_session.set_execute_result(user)
    res = await crud.get_user_by_email(fake_session, "u@example.com")
    assert res is user


@pytest.mark.asyncio
async def test_get_user_by_email_not_found(monkeypatch, fake_session, fake_user_class, stub_select):
    fake_session.set_execute_result(None)
    res = await crud.get_user_by_email(fake_session, "nope@example.com")
    assert res is None


# ----------------- create_user -----------------

@pytest.mark.asyncio
async def test_create_user_success(monkeypatch, fake_session, fake_user_class):
    # Patch password hashing
    monkeypatch.setattr(crud, "get_password_hash", lambda p: f"HASH({p})")

    # Prepare input schema stub
    data = SimpleNamespace(email="new@example.com", password="secret")

    created = await crud.create_user(fake_session, data)

    assert isinstance(created, fake_user_class)
    assert created.email == "new@example.com"
    assert created.hashed_password == "HASH(secret)"
    # Side effects
    assert fake_session.commits == 1
    assert fake_session.rollbacks == 0
    assert created in fake_session.refreshed
    assert any(u.email == "new@example.com" for u in fake_session.added)


@pytest.mark.asyncio
async def test_create_user_integrity_error_rolls_back(monkeypatch, fake_session, fake_user_class):
    # Make commit raise IntegrityError
    async def bad_commit():
        raise IntegrityError("stmt", "params", orig=None)
    monkeypatch.setattr(fake_session, "commit", bad_commit)

    data = SimpleNamespace(email="dup@example.com", password="x")
    with pytest.raises(IntegrityError):
        await crud.create_user(fake_session, data)
    assert fake_session.rollbacks == 1


@pytest.mark.asyncio
async def test_create_user_sqlalchemy_error_rolls_back(monkeypatch, fake_session, fake_user_class):
    async def bad_commit():
        raise SQLAlchemyError("boom")
    monkeypatch.setattr(fake_session, "commit", bad_commit)

    data = SimpleNamespace(email="oops@example.com", password="x")
    with pytest.raises(SQLAlchemyError):
        await crud.create_user(fake_session, data)
    assert fake_session.rollbacks == 1


# ----------------- get_current_user -----------------

@pytest.mark.asyncio
async def test_get_current_user_ok(monkeypatch, fake_session, fake_user_class, stub_select):
    monkeypatch.setattr(crud, "jwt", SimpleNamespace(decode=lambda *_a, **_k: {"sub": "123"}))
    user = fake_user_class(email="ok@example.com", id=123)
    fake_session.set_execute_result(user)

    got = await crud.get_current_user(token="BearerToken", db=fake_session)
    assert got is user


@pytest.mark.asyncio
async def test_get_current_user_bad_token_raises_401(monkeypatch, fake_session):
    def raise_jwt(*a, **k):
        raise JWTError("invalid")
    monkeypatch.setattr(crud, "jwt", SimpleNamespace(decode=raise_jwt))

    with pytest.raises(HTTPException) as ei:
        await crud.get_current_user(token="BAD", db=fake_session)
    assert ei.value.status_code == 401
    assert "Could not validate credentials" in ei.value.detail


@pytest.mark.asyncio
async def test_get_current_user_missing_sub_raises_401(monkeypatch, fake_session):
    monkeypatch.setattr(crud, "jwt", SimpleNamespace(
        decode=lambda *a, **k: {"nope": "x"}
    ))
    with pytest.raises(HTTPException) as ei:
        await crud.get_current_user(token="t", db=fake_session)
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_user_not_found_raises_401(monkeypatch, fake_session):
    monkeypatch.setattr(crud, "jwt", SimpleNamespace(
        decode=lambda *a, **k: {"sub": "777"}
    ))
    fake_session.set_execute_result(None)  # no user
    with pytest.raises(HTTPException) as ei:
        await crud.get_current_user(token="t", db=fake_session)
    assert ei.value.status_code == 401


# ----------------- benchmark_or_auth -----------------

@pytest.mark.asyncio
async def test_benchmark_or_auth_returns_benchmarkuser_when_flag_set(monkeypatch, fake_session):
    # token is optional; flag forces BenchmarkUser
    req = Request(scope={"type": "http"})
    req.state.is_benchmark = True
    got = await crud.benchmark_or_auth(request=req, token=None, db=fake_session)
    assert isinstance(got, crud.BenchmarkUser.__class__) or getattr(got, "email", "") == "benchmark@local"
    assert got.id == 0
    assert got.email == "benchmark@local"
    assert "benchmark" in got.roles

@pytest.mark.asyncio
async def test_benchmark_or_auth_delegates_to_get_current_user(monkeypatch, fake_session, fake_user_class):
    # No benchmark flag; ensure it calls get_current_user with our token/db
    called = {}

    async def fake_get_current_user(token, db):
        called["token"] = token
        called["db"] = db
        return fake_user_class(email="x@example.com", id=5)

    monkeypatch.setattr(crud, "get_current_user", fake_get_current_user)

    req = Request(scope={"type": "http"})
    # no req.state.is_benchmark set ⇒ False by default
    user = await crud.benchmark_or_auth(request=req, token="Tok", db=fake_session)
    assert user.email == "x@example.com"
    assert called["token"] == "Tok"
    assert called["db"] is fake_session
