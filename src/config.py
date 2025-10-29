# src/config.py
# Configuration settings for the FastAPI application using Pydantic BaseSettings.


###### IMPORT TOOLS ######
# global imports
import os
import json
import pathlib as pl
from functools import lru_cache
from pydantic import field_validator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


###### BASEDIR ######
PROJECT_ROOT = pl.Path(__file__).resolve().parent.parent
BASE_DIR = str(PROJECT_ROOT)


###### SETTINGS ######
class Settings(BaseSettings):
    """Application configuration settings."""
    # app
    API_PORT: str = "8002"
    API_HOST: str = "0.0.0.0"
    APP_ENV: str = Field("dev", pattern="^(dev|prod|test)$")
    BENCHMARK_TOKEN: str | None = None
    # debug
    DEBUG: bool = False
    LOG_DIR: str = os.path.join(BASE_DIR, "src", "logs")
    LOG_FILE: str = os.path.join(BASE_DIR, "src", "logs", "app.log")
    # security
    SECRET_KEY: str = "change-me"
    JWT_ALG: str = "HS256"
    ACCESS_TTL_MIN: int = 15
    REFRESH_TTL_DAYS: int = 7
    ACCESS_SECRET: str = "access-secret"
    REFRESH_SECRET: str = "refresh-secret"
    JWT_ISSUER: str = "your-auth"
    JWT_AUDIENCE: str = "auth_api"
    # urls
    API_PREFIX: str = ""
    # dirs
    STATIC_DIR: str = os.path.join(BASE_DIR, "static")
    # database
    POSTGRES_DB: str = "robomate"
    POSTGRES_USER: str = "robomate"
    POSTGRES_PASSWORD: str = "robomate"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_CONTAINER_NAME: str = "postgres"
    POSTGRES_ALEMBIC_URL: str = ""
    USER_DB_URL: str = ""
    DB_ADMIN_URL: str | None = ""
    # CORS
    CORS_ORIGINS: list[str] = ["*"]
    # redis
    TOKEN_CACHE_PREFIX: str = "fapi-tokens"
    REDIS_URL: str = "redis://localhost:6379/0"
    ACCESS_TOKEN_TTL_SEC: int = 900
    REFRESH_TOKEN_TTL_SEC: int = 60 * 60 * 24
    RATE_LIMIT_PREFIX: str = "fapi-limiter"
    # timezone
    TIMEZONE: str = "Europe/Kyiv"
    # metrics
    METRICS_HOST: str = "0.0.0.0"
    METRICS_PORT: str = "8003"
    METRICS_PATH: str = "/metrics"


    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from various formats."""
        if v is None or v == "":
            return []
        if isinstance(v, (list, tuple, set)):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            s = v.strip()
            if s == "*":
                return ["*"]
            if (s.startswith("[") and s.endswith("]")) or (
                s.startswith("(") and s.endswith(")")
            ):
                try:
                    data = json.loads(s)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON in CORS_ORIGINS: {e}") from e
                if not isinstance(data, list):
                    raise ValueError("CORS_ORIGINS JSON must be a list")
                return [str(x).strip() for x in data if str(x).strip()]
            return [part.strip() for part in s.split(",") if part.strip()]
        raise TypeError("CORS_ORIGINS must be a list or a comma-separated string")


# Create settings instance
@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    env = os.getenv("APP_ENV", "dev")
    env_file = PROJECT_ROOT / f".env.{env}"
    return Settings(_env_file=env_file)
