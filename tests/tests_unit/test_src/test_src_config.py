# ./tests/test_src/test_src_config.py

###### IMPORT TOOLS ######
# global imports
import sys
import pytest


###### HELPER FUNCTION ######
def _fresh_get_settings():
    """Import src.config and return a fresh get_settings function"""
    sys.modules.pop("src.config", None)
    import src.config as config
    config.get_settings.cache_clear()
    return config.get_settings


###### TESTS ######
@pytest.mark.parametrize(
    "raw_env, expected",
    [
        ('["*"]', ["*"]),
        ('["http://a.com","http://b.com"]', ["http://a.com", "http://b.com"]),
        (None, ["*"]),
    ],
)
def test_cors_origins_parsing(monkeypatch, raw_env, expected):
    """Test parsing of CORS_ORIGINS from environment variable."""
    get_settings = _fresh_get_settings()
    monkeypatch.delenv("APP_ENV", raising=False)

    if raw_env is None:
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("CORS_ORIGINS", raw_env)

    settings = get_settings()
    assert settings.CORS_ORIGINS == expected


def test_defaults_and_env_override(monkeypatch, tmp_path):
    """Test that defaults are used and overridden by .env files."""
    env_text = "\n".join([
        "API_PORT=9000",
        "DEBUG=true",
        "API_PREFIX=/api",
        'CORS_ORIGINS=["http://localhost","http://127.0.0.1"]',
    ])
    for k in ["API_PORT", "DEBUG", "API_PREFIX", "CORS_ORIGINS"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("APP_ENV", "test")
    sys.modules.pop("src.config", None)

    import src.config as config
    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / ".env.test").write_text(env_text, encoding="utf-8")
    config.PROJECT_ROOT = proj
    config.BASE_DIR = str(proj)
    config.get_settings.cache_clear()

    settings = config.get_settings()
    assert settings.API_PORT == "9000"
    assert settings.DEBUG is True
    assert settings.API_PREFIX == "/api"
    assert settings.CORS_ORIGINS == ["http://localhost", "http://127.0.0.1"]
    assert settings.API_HOST == "0.0.0.0"


def test_lru_cache_and_cache_clear(monkeypatch, tmp_path):
    """Test that get_settings uses LRU cache and cache_clear works."""
    for k in ["API_PORT", "DEBUG", "API_PREFIX", "CORS_ORIGINS"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("APP_ENV", "test")

    sys.modules.pop("src.config", None)
    import src.config as config

    proj = tmp_path / "proj2"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / ".env.test").write_text("API_PORT=8008\nAPI_PREFIX=/v1", encoding="utf-8")

    config.PROJECT_ROOT = proj
    config.BASE_DIR = str(proj)
    config.get_settings.cache_clear()

    settings_1 = config.get_settings()
    assert settings_1.API_PORT == "8008"
    assert settings_1.API_PREFIX == "/v1"

    (proj / ".env.test").write_text("API_PORT=8010\nAPI_PREFIX=/v2", encoding="utf-8")
    config.get_settings.cache_clear()

    settings_2 = config.get_settings()
    assert settings_2.API_PORT == "8010"
    assert settings_2.API_PREFIX == "/v2"

    assert settings_1 is not settings_2


def test_empty_app_env_uses_defaults(monkeypatch):
    """Test that with no APP_ENV and no CORS_ORIGINS, defaults are used."""
    get_settings = _fresh_get_settings()
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = get_settings()
    assert settings.CORS_ORIGINS == ["*"]
    assert isinstance(settings.DEBUG, bool)
