# tests/test_endpoint_events/test_endpoint_events_schemas.py

###### IMPORT TOOLS ######
# global imports
import pytest
from uuid import uuid4
from datetime import datetime
from pydantic import ValidationError

# local imports
from src.endpoint_events import schemas


###### HELPERS ######
def make_event(**overrides):
    """Helper to build a valid event dict quickly."""
    data = {
        "event_id": str(uuid4()),
        "occurred_at": datetime.utcnow().isoformat(),
        "user_id": 123,
        "event_type": "purchase",
        "properties": {"price": 10.5, "currency": "USD"},
    }
    data.update(overrides)
    return data


###### TESTS ######
def test_eventbase_valid_parsing():
    event_dict = make_event()
    model = schemas.EventBase(**event_dict)
    assert isinstance(model.event_id, type(uuid4()))
    assert isinstance(model.occurred_at, datetime)
    assert model.user_id == 123
    assert model.event_type == "purchase"
    assert model.properties == {"price": 10.5, "currency": "USD"}


def test_eventbase_default_properties():
    event_dict = make_event(properties=None)
    event_dict.pop("properties", None)
    model = schemas.EventBase(**event_dict)
    assert model.properties == {}


def test_eventbase_invalid_uuid_or_datetime():
    bad_uuid = make_event(event_id="not-a-uuid")
    with pytest.raises(ValidationError):
        schemas.EventBase(**bad_uuid)

    bad_date = make_event(occurred_at="2025-13-99")
    with pytest.raises(ValidationError):
        schemas.EventBase(**bad_date)


def test_eventbase_event_type_length_limit():
    too_long = "x" * 200
    bad_event = make_event(event_type=too_long)
    with pytest.raises(ValidationError):
        schemas.EventBase(**bad_event)


def test_eventsin_valid_list_of_events():
    e1 = make_event()
    e2 = make_event(event_type="view")
    wrapper = schemas.EventsIn(input_value=[e1, e2])
    assert len(wrapper.input_value) == 2
    assert all(isinstance(e, schemas.EventBase) for e in wrapper.input_value)


def test_eventsout_valid_output():
    inserted = [uuid4(), uuid4()]
    duplicates = [uuid4()]
    result = schemas.EventsOut(inserted=inserted, duplicates=duplicates)
    assert result.inserted == inserted
    assert result.duplicates == duplicates


def test_eventsout_invalid_uuid_list():
    with pytest.raises(ValidationError):
        schemas.EventsOut(inserted=["not-uuid"], duplicates=[])
