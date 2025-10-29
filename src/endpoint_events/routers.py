# src/endpoint_events/routers.py
# This module contains the API router for managing events, including adding new endpoint_events with conflict handling.


###### IMPORT TOOLS ######
# global imports
import logging
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from fastapi_limiter.depends import RateLimiter

# local imports
from src.user_auth import schemas
from src.data_base.db import AsyncSession
from src.data_base.models import Events
from src.endpoint_events import schemas
from src.infrastructure.resources import resources
from src.infrastructure.metrics import record_event


###### LOGGER ######
logger = logging.getLogger("app.endpoint_events.routers")

###### CREATE ROUTER ######
router = APIRouter(prefix="/events")

###### EVENT ######
@router.post(
    "/",
    response_model=schemas.EventsOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RateLimiter(times=5, seconds=60))],
)
async def add_unique_events(
    events: List[schemas.EventBase],
    db: AsyncSession = Depends(resources.get_session)
):
    '''Add new events to the database.'''
    # Check if events list is empty
    if not events:
        logging.info("No events provided for insertion.")
        return schemas.EventsOut(inserted=[], duplicates=[])

    # Prepare payload and extract event IDs
    payload = [event.model_dump() for event in events]
    input_ids = {event["event_id"] for event in payload}

    # Insert events with conflict handling
    stmt = (
        pg_insert(Events)
        .values(payload)
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(Events.event_id)
    )
    result = await db.execute(stmt)
    await db.commit()

    # Get inserted IDs and determine duplicates
    inserted_ids = {row[0] for row in result.fetchall()}
    duplicates_ids = input_ids - inserted_ids
    logger.info("Inserted %d events, %d duplicates found.", len(inserted_ids), len(duplicates_ids))
    record_event({"name": "events_main"})
    return schemas.EventsOut(
        inserted=list(inserted_ids),
        duplicates=list(duplicates_ids)
    )
