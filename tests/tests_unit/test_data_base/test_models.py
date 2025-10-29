# ./tests/test_data_base/test_models.py

####### IMPORT TOOLS ######
# global imports
from sqlalchemy.dialects.postgresql import UUID as PgUUID, JSON as PgJSON
from sqlalchemy import DateTime, String, Integer, Index

# local imports
from src.data_base.models import User, Events

####### TESTS FOR USER AND EVENTS MODELS ######
def test_user_table_name_and_columns_exist():
    """Check User model table name and columns."""
    t = User.__table__
    assert t.name == "users"

    for col in ("id", "email", "hashed_password", "created_at", "updated_at", "last_activity_at"):
        assert col in t.c, f"Column {col} should exist on users"

    assert isinstance(t.c.id.type, Integer), "id should be Integer PK"
    assert isinstance(t.c.email.type, String), "email should be String"
    assert t.c.email.type.length == 320, "email length should be 320"

    assert isinstance(t.c.hashed_password.type, String), "hashed_password should be String"
    assert t.c.hashed_password.type.length == 255, "hashed_password length should be 255"

    assert isinstance(t.c.created_at.type, DateTime), "created_at should be DateTime"
    assert t.c.created_at.type.timezone is True, "created_at should be timezone-aware"

    assert isinstance(t.c.updated_at.type, DateTime), "updated_at should be DateTime"
    assert t.c.updated_at.type.timezone is True, "updated_at should be timezone-aware"

    assert isinstance(t.c.last_activity_at.type, DateTime), "last_activity_at should be DateTime"
    assert t.c.last_activity_at.type.timezone is True, "last_activity_at should be timezone-aware"

    assert t.c.email.nullable is False
    assert t.c.hashed_password.nullable is False
    assert t.c.created_at.nullable is False
    assert t.c.updated_at.nullable in (True, None)
    assert t.c.last_activity_at.nullable in (True, None)


def test_user_indexes_and_uniqueness():
    """Check indexes and uniqueness constraints on User model."""
    idx_names = {ix.name: ix for ix in User.__table__.indexes}
    assert "uq_users_email_active_only" in idx_names, "Unique index on email should exist"
    email_idx: Index = idx_names["uq_users_email_active_only"]
    assert email_idx.unique is True, "Email index must be unique"
    assert len(email_idx.expressions) == 1
    assert str(email_idx.expressions[0].name) == "email"


def test_events_table_name_and_columns_exist():
    """Check Events model table name and columns."""
    t = Events.__table__
    assert t.name == "events"

    for col in ("event_id", "occurred_at", "user_id", "event_type", "properties"):
        assert col in t.c, f"Column {col} should exist on events"

    assert isinstance(t.c.event_id.type, PgUUID), "event_id should be PostgreSQL UUID"
    assert getattr(t.c.event_id.type, "as_uuid", False) is True, "UUID should use as_uuid=True"

    assert isinstance(t.c.occurred_at.type, DateTime), "occurred_at should be DateTime"
    assert t.c.occurred_at.type.timezone is True, "occurred_at should be timezone-aware"

    assert isinstance(t.c.user_id.type, Integer), "user_id should be Integer"
    assert isinstance(t.c.event_type.type, String), "event_type should be String"
    assert t.c.event_type.type.length == 100, "event_type length should be 100"

    assert isinstance(t.c.properties.type, PgJSON), "properties should be PostgreSQL JSON"

    assert t.c.event_id.nullable is False
    assert t.c.occurred_at.nullable is False
    assert t.c.user_id.nullable is False
    assert t.c.event_type.nullable is False
    assert t.c.properties.nullable is True


def test_primary_keys_defined():
    """Check primary keys for User and Events models."""
    user_pk_cols = [col.name for col in User.__table__.primary_key.columns]
    assert user_pk_cols == ["id"], "User primary key should be 'id'"

    events_pk_cols = [col.name for col in Events.__table__.primary_key.columns]
    assert events_pk_cols == ["event_id"], "Events primary key should be 'event_id'"


def test_server_defaults_present_where_expected():
    """Check server_default presence for time columns."""
    u = User.__table__.c
    e = Events.__table__.c

    assert u.created_at.server_default is not None, "User.created_at should have server_default"
    assert u.updated_at.server_default is not None, "User.updated_at should have server_default"
    assert e.occurred_at.server_default is not None, "Events.occurred_at should have server_default"
