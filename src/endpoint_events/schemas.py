# src/endpoint_events/schemas.py
# This module defines Pydantic schemas for event data handling.


###### IMPORT TOOLS ######
# global imports
from uuid import UUID
from datetime import datetime
from typing import Dict, List
from pydantic import (
    BaseModel,
    Field,
    JsonValue,
)


###### EVENTS ######
# Schema representing a single event
class EventBase(BaseModel):
    event_id: UUID = Field(..., description="Unique identifier for the event")
    occurred_at: datetime = Field(..., description="Timestamp when the event occurred")
    user_id: int = Field(..., description="Identifier of the user associated with the event")
    event_type: str = Field(..., max_length=100, description="Type of the event")
    properties: Dict[str, JsonValue] = Field(default_factory=dict, description="Additional properties of the event")

# Schema for inputting multiple events
class EventsIn(BaseModel):
    input_value: List[EventBase] = Field(..., description="List of events to be processed")

# Schema for outputting inserted event IDs and duplicates
class EventsOut(BaseModel):
     inserted: List[UUID] = Field(..., description="List of successfully inserted event IDs")
     duplicates: List[UUID] = Field(..., description="List of duplicate event IDs that were not inserted")
