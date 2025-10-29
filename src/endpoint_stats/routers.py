# src/endpoint_events/routers.py
# This module contains the API router for managing event`s statistic.


###### IMPORT TOOLS ######
# global imports
import logging
from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import select, func, literal

# local imports
from src.data_base.db import AsyncSession
from src.data_base.models import Events, User
from src.infrastructure.resources import resources
from src.data_base.crud import get_current_user, benchmark_or_auth
from src.endpoint_stats.utils import get_first_visit_users, cohort_week_active_count
from src.infrastructure.metrics import record_event


###### LOGGER ######
logger = logging.getLogger("app.endpoint_stats.routers")

###### CREATE ROUTER ######
router = APIRouter(prefix="/stats")

###### Daily Active Users ######
@router.get(
    "/dau",
    dependencies=[Depends(RateLimiter(times=5, seconds=60))],
)
async def get_dau(
        from_date: date = Query(..., alias="from", description="Start date (YYYY-MM-DD)"),
        to_date: date =  Query(..., alias="to", description="Final date (YYYY-MM-DD)"),
        segment: str | None = Query(None,description="Optional segment filter, e.g. event_type:purchase or properties.country=UA",),
        current_user: User = Depends(benchmark_or_auth),
        db: AsyncSession = Depends(resources.get_session),
):
    # Validate date range
    if from_date > to_date:
        logger.warning("User ID %d provide 'from' date greater than 'to' date for DAU calculation.",(current_user.id))
        raise HTTPException(status_code=400, detail="'from' date must be earlier than or equal to 'to' date.")

    # Query daily active users
    statement = (
        select(
            func.date(Events.occurred_at).label("day"),
            func.count(func.distinct(Events.user_id)).label("dau")
        )
        .where(Events.occurred_at.between(from_date, to_date))
        .group_by(func.date(Events.occurred_at))
        .order_by(func.date(Events.occurred_at))
    )

    # Apply segment filter if provided
    if segment:
        try:
            if ":" in segment:
                key, value = segment.split(":", 1)
            elif "=" in segment:
                key, value = segment.split("=", 1)
            else:
                raise ValueError
            if key.startswith("properties."):
                prop_key = key.split(".", 1)[1]
                statement = statement.where(Events.properties[prop_key].astext == value)
            else:
                statement = statement.where(getattr(Events, key) == value)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid segment format")

    # Execute query and format results
    rows = (await db.execute(statement)).all()
    logger.info("User ID %d retrieved DAU from %s to %s.", current_user.id, from_date, to_date)
    record_event({"name": "stats_dau"})
    return {str(day): dau for day, dau in rows}


###### TOP EVENTS ######
@router.get(
    "/top-events",
    dependencies=[Depends(RateLimiter(times=5, seconds=60))],
)
async def get_top_events(
        limit: int = Query(10, ge=1, le=100, description="Number of top events to retrieve"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(resources.get_session),
):
    # Query top events
    statement = (
        select(
            Events.event_type,
            func.count(Events.event_id).label("count")
        )
        .group_by(Events.event_type)
        .order_by(func.count(Events.event_id).desc())
        .limit(limit)
    )
    rows = (await db.execute(statement)).all()
    logger.info("User ID %d retrieved top %d events.", current_user.id, limit)
    record_event({"name": "top-events"})
    return [{ "event_type": event_type, "count": count } for event_type, count in rows]


####### COHORT ANALYSIS ######
@router.get(
    "/retention",
    dependencies=[Depends(RateLimiter(times=5, seconds=60))],
)
async def get_cohort_analysis(
        start_date: date = Query(..., description="Cohort analysis start date (YYYY-MM-DD)"),
        window: int = Query(4, ge=1, le=52, description="Number of weeks for cohort analysis"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(resources.get_session),
):
    # Validate start date
    if start_date > date.today():
        logger.warning("User ID %d provided a future start date for cohort analysis.", current_user.id)
        raise HTTPException(status_code=400, detail="Start date cannot be in the future.")

    # Get users who were first active on the start date
    first_users_sq = await get_first_visit_users(start_date)
    users_count = (await db.execute(
        select(func.count()).select_from(first_users_sq)
    )).scalar_one()

    if users_count == 0:
        logger.info("User ID %d found no users for cohort analysis starting from %s.", current_user.id, start_date)
        return {"details" : f"No first visit users on {literal(start_date)}"}

    # Calculate weekly retention
    weeks = []
    for week in range(window):
        week_stats = await cohort_week_active_count(
            first_users_sq, start_date, db, week, users_count
        )
        week_stats["week_num"] = week
        weeks.append(week_stats)
    logger.info("User ID %d retrieved cohort analysis starting from %s for %d weeks.", current_user.id, start_date, window)
    record_event({"name": "stats_retention"})
    return {"start_date": str(start_date), "window": window, "cohort_size": users_count, "weeks": weeks}
