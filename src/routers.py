# src/routers.py
# This module defines the main API router for the application,


###### IMPORT TOOLS ######
from fastapi import APIRouter
from src.config import get_settings

from src.user_auth.routers import router as user_auth_router
from src.endpoint_events.routers import router as event_router
from src.endpoint_stats.routers import router as stats_router


# create main api router
api_router = APIRouter(prefix=get_settings().API_PREFIX)
api_router.include_router(user_auth_router, tags=["auth"])
api_router.include_router(event_router, tags=["events"])
api_router.include_router(stats_router, tags=["stats"])


# export api router
__all__ = ["api_router"]
