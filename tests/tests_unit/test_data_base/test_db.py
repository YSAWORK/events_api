import importlib
import sys
from types import SimpleNamespace

import pytest


def _fresh_import(monkeypatch, url: str = "postgresql+asyncpg://u:p@h:5432/db"):
    """
    Import src.data_base.db with all side effects intercepted:
    - get_settings().USER_DB_URL -> url
    - sqlalchemy.ext.asyncio.create_async_engine -> fake recorder
    - sqlalchemy.ext.asyncio.async_sessionmaker -> fake recorder
    Returns (db_module, spies)
    """
    # --- Prepare spies/fakes ---
    calls = {}

    class FakeEngine:
        pass

    def fake_create_async_engine(got_url, **kwargs):
        calls["engine"] = {"url": got_url, "kwargs": kwargs}
        return FakeEngine()

    def fake_async_sessionmaker(*args, **kwargs):
        calls["sessionmaker"] = {"args": args, "kwargs": kwargs}
        # Return any sentinel object to stand in for the factory
        return SimpleNamespace(__name__="FakeSessionFactory")

    # Patch upstream imports BEFORE importing the module under test
    import sqlalchemy.ext.asyncio as sa_asyncio
    monkeypatch.setattr(
        sa_asyncio, "create_async_engine", fake_create_async_engine, raising=True
    )
    monkeypatch.setattr(
        sa_asyncio, "async_sessionmaker", fake_async_sessionmaker, raising=True
    )

    # Patch get_settings() to return our URL
    import src.config as cfg
    monkeypatch.setattr(
        cfg, "get_settings", lambda: SimpleNamespace(USER_DB_URL=url), raising=True
    )

    # Ensure a clean import (module executes top-level code at import time)
    sys.modules.pop("src.data_base.db", None)
    import src.data_base.db as db

    return db, calls


def test_engine_is_created_with_pool_pre_ping(monkeypatch):
    url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
    db, calls = _fresh_import(monkeypatch, url=url)

    # Engine instance created
    assert "engine" in calls
    assert calls["engine"]["url"] == url
    assert calls["engine"]["kwargs"].get("pool_pre_ping") is True

    # Module exposes the fake engine instance
    from sqlalchemy.ext.asyncio import AsyncSession
    assert hasattr(db, "engine")
    assert hasattr(db, "AsyncSessionLocal")

    # Session maker called with expected params
    sm = calls.get("sessionmaker")
    assert sm is not None
    # async_sessionmaker(*args, **kwargs) was called with only kwargs in our module
    assert sm["kwargs"]["bind"] is db.engine
    assert sm["kwargs"]["class_"] is AsyncSession
    assert sm["kwargs"]["expire_on_commit"] is False


def test_base_is_declarative_and_abstract(monkeypatch):
    db, _ = _fresh_import(monkeypatch)
    from sqlalchemy.orm import DeclarativeBase

    assert issubclass(db.Base, DeclarativeBase)
    # Explicitly marked abstract so models inherit properly
    assert getattr(db.Base, "__abstract__", None) is True


def test_reimport_uses_new_url(monkeypatch):
    """If settings change, a fresh import should pick up the new URL."""
    first_url = "postgresql+asyncpg://u1:p1@h:5432/db1"
    db1, calls1 = _fresh_import(monkeypatch, url=first_url)
    assert calls1["engine"]["url"] == first_url

    second_url = "postgresql+asyncpg://u2:p2@h:5432/db2"
    db2, calls2 = _fresh_import(monkeypatch, url=second_url)
    assert calls2["engine"]["url"] == second_url
    # Ensure we actually got a new engine object on re-import
    assert db1.engine is not db2.engine
