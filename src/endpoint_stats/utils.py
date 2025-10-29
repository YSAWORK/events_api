# ./src/endpoint_stats/utils.py
# This module contains utility functions for statistics calculations, such as cohort analysis.


####### IMPORT TOOLS ########
# global imports
from datetime import date, timedelta

from sqlalchemy import select, func, cast, Date, literal, distinct

# local imports
from src.data_base.models import Events
from src.data_base.db import AsyncSession
from src.config import get_settings


##### FUNCTION TO GET USERS WITH FIRST VISIT ON A GIVEN DATE ######
async def get_first_visit_users(start_date: date):
    app_timezone = get_settings().TIMEZONE
    first_visit_statement = (
            select(Events.user_id)
            .group_by(Events.user_id)
            .having(
                cast(func.timezone(app_timezone, func.min(Events.occurred_at)), Date)
                == literal(start_date)
            )
        )
    return first_visit_statement


##### FUNCTION TO GET WEEKLY ACTIVE USERS IN A COHORT ######
async def cohort_week_active_count(users, start_date: date, database_session: AsyncSession, week_num: int, users_count: int) -> dict:
    week_start = start_date + timedelta(days=7 * week_num + 1)
    week_end   = week_start + timedelta(days=7)
    app_timezone = get_settings().TIMEZONE

    week_unique_users_statement = (
        select(func.count(distinct(Events.user_id)))
        .where(
            Events.user_id.in_(select(users.c.user_id)),
            cast(func.timezone(app_timezone, Events.occurred_at), Date) >= literal(week_start),
            cast(func.timezone(app_timezone, Events.occurred_at), Date) <  literal(week_end),
        )
    )
    week_active_users_count = (await database_session.execute(
        week_unique_users_statement
    )).scalar_one()

    return {
        "period": f"{week_start} - {week_end - timedelta(days=1)}",
        "week_active_users": int(week_active_users_count),
        "percent": round((week_active_users_count / users_count) * 100, 2),
    }