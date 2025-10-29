# ./tests/test_src/test_src_main.py


###### IMPORT TOOLS ######
# global imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Mount


def test_app_created(fresh_app_factory):
    """Check that the FastAPI app is created successfully."""
    app, _ = fresh_app_factory()
    assert isinstance(app, FastAPI)


def test_root_redirect_in_debug(monkeypatch, fresh_app_factory):
    """When DEBUG=1, root should redirect (302) or return 200."""
    monkeypatch.setenv("DEBUG", "1")
    app, stub = fresh_app_factory()
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code in (200, 302)
    assert stub.start and stub.stop


def test_root_status_when_debug_false(monkeypatch, fresh_app_factory):
    """When DEBUG=0, root should return status ok."""
    monkeypatch.setenv("DEBUG", "0")
    app, stub = fresh_app_factory()
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
    assert stub.start and stub.stop


def test_cors_middleware_present(fresh_app_factory):
    """Check that CORSMiddleware is added to the app."""
    app, _ = fresh_app_factory()
    assert any(m.cls is CORSMiddleware for m in app.user_middleware)


def test_static_files_mounted(fresh_app_factory):
    """Check that static files are mounted at /static."""
    app, _ = fresh_app_factory()
    mounts = [r for r in app.router.routes if isinstance(r, Mount)]
    assert any(m.path == "/static" for m in mounts)


def test_benchmark_middleware_added(fresh_app_factory):
    """Check that benchmark token middleware is added to the app."""
    app, _ = fresh_app_factory()
    assert any(m.cls is BaseHTTPMiddleware for m in app.user_middleware)
