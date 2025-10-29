# tests/test_src/test_src_routers.py

###### IMPORT TOOLS ######
# global imports
from fastapi import APIRouter

# local imports
from src.routers import api_router
from src.config import get_settings


###### TESTS FOR MAIN ROUTERS ######
def test_api_router_is_instance():
    """api_router must be an instance of APIRouter."""
    assert isinstance(api_router, APIRouter)


def test_api_router_prefix_matches_settings():
    """Check that api_router prefix matches API_PREFIX from settings."""
    settings = get_settings()
    assert api_router.prefix == settings.API_PREFIX
    if settings.API_PREFIX:
        assert api_router.prefix.startswith("/")


def test_api_router_has_expected_tags():
    """Check that api_router includes expected tags."""
    tags = set()
    for route in api_router.routes:
        tags.update(route.tags or [])
    assert {"auth", "events", "stats"}.issubset(tags)


def test_api_router_has_routes():
    """Check that api_router has at least one route defined."""
    assert len(api_router.routes) > 0
    for route in api_router.routes:
        assert hasattr(route, "path")
        assert route.path.startswith("/")


def test_api_router_exports():
    """Check that api_router is exported in src.routers.__all__."""
    from src import routers
    assert "api_router" in routers.__all__
