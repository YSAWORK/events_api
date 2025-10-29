# ./src/infrastructure/cache.py
# This module provides a Cache class for managing key-value pairs in Redis with TTL support.


####### IMPORT TOOLS #######
# global imports
from aiocache import caches

# local imports
from src.config import get_settings


####### SETUP AIOCACHE #######
def setup_aiocache():
    '''Setup aiocache with Redis backend and JSON serialization.'''
    settings = get_settings()
    caches.set_config(
        {
            "default": {
                "cache": "aiocache.RedisCache",
                "endpoint": settings.REDIS_URL,
                "serializer": {"class": "aiocache.serializers.JsonSerializer"},
                "namespace": "rq",
                "timeout": 1,
            }
        }
    )
