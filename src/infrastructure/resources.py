# .src/infrastructure/resources.py
# This module manages shared resources such as database connections, Redis clients, and HTTP clients.


###### IMPORT TOOLS ######
# global imports
import logging, asyncio, httpx
from typing import AsyncGenerator
from redis import asyncio as aioredis
from aioprometheus.service import Service
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request

# local imports
from src.config import get_settings
from src.infrastructure import cache
from src.data_base.db import AsyncSessionLocal, engine
from src.infrastructure.metrics import _update_events_per_second, events_per_second


###### LOGGER ######
logger = logging.getLogger("app.infrastructure.resources")

###### RESOURCES ######
class Resources:
    """Manages shared resources like DB, Redis, and HTTP clients."""
    def __init__(self):
        self.engine = engine
        self.session_maker = AsyncSessionLocal
        self.redis: aioredis.Redis | None = None
        self.http: httpx.AsyncClient | None = None
        self.metrics_service: Service | None = None
        self.metrics_task: asyncio.Task | None = None
        self._started = False

    async def start(self):
        """Initialize resources if not already started."""
        if self._started:
            return
        self.redis = aioredis.from_url(
            get_settings().REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=30,
            max_connections=50,
        )
        await self.redis.ping()
        cache.setup_aiocache()
        self.http = httpx.AsyncClient()
        await self.start_metrics()
        events_per_second.set({}, 0.0)
        self._started = True
        logger.info("Resources started.")


    async def stop(self):
        """Clean up resources if they were started."""
        if not self._started:
            return
        if self.http:
            await self.http.aclose()
        if self.redis:
            await self.redis.aclose()
            self.redis = None
        if self.metrics_service:
            await self.metrics_service.stop()
        if self.metrics_task:
            self.metrics_task.cancel()
        await self.engine.dispose()
        self._started = False
        logger.info("Resources stopped.")

    async def start_metrics(self):
        """Start Prometheus metrics service and background EPS updater."""
        settings = get_settings()
        service = Service()
        await service.start(addr=settings.API_HOST, port=int(settings.METRICS_PORT))
        task = asyncio.create_task(_update_events_per_second())
        self.metrics_service = service
        self.metrics_task = task
        logger.info("Metrics service started on %s:%s", settings.METRICS_HOST, settings.METRICS_PORT)

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a new database session."""
        async with self.session_maker() as s:
            yield s


# Singleton instance of Resources
resources = Resources()

# Middleware to allow benchmark token to bypass auth
async def benchmark_token_middleware(request: Request, call_next):
    """Allow requests with BENCHMARK_TOKEN to bypass auth."""
    auth = request.headers.get("Authorization")
    if not request.url.path.startswith(("/stats",)):
        return await call_next(request)
    if auth and auth.startswith("Bearer "):
        token = auth.split("Bearer ")[1]
        test_token = get_settings().BENCHMARK_TOKEN
        if test_token and token == test_token:
            request.state.is_benchmark = True
    return await call_next(request)

# Dependency for FastAPI routes
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get a DB session, ensuring resources are started."""
    if not resources._started:
        await resources.start()
    async for s in resources.get_session():
        yield s
