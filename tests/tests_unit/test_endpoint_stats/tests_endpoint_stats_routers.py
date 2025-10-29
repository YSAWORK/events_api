# ./tests/test_endpoint_stats/tests_endpoint_stats_routers.py

import pytest
from datetime import date, timedelta
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select, literal, union_all

# Імпортуємо функції для тестування
from src.endpoint_events.routers import (
    get_dau,
    get_top_events,
    get_cohort_analysis,
)
# Також імпортуємо сам модуль, щоб мати змогу підміняти функції (monkeypatch)
import src.endpoint_events.routers as routers_mod


# ---------- Підготовка допоміжних класів ----------

class _ExecResult:
    """Імітація результату виконання SQL-запиту (аналог AsyncResult)."""
    def __init__(self, rows=None, scalar=None):
        self._rows = rows
        self._scalar = scalar

    def all(self):
        return self._rows or []

    def scalar_one(self):
        return self._scalar


class FakeDB:
    """
    Простий фейковий асинхронний сеанс БД.
    Повертає заздалегідь підготовлені rows або scalar.
    """
    def __init__(self, *, rows=None, scalar=None):
        self._rows = rows
        self._scalar = scalar
        self.last_statement = None

    async def execute(self, statement):
        self.last_statement = statement
        if self._rows is not None:
            return _ExecResult(rows=list(self._rows))
        return _ExecResult(scalar=self._scalar)


class DummyUser(SimpleNamespace):
    """Простий об’єкт користувача лише з полем id."""
    pass


# ---------- Тести get_dau ----------

@pytest.mark.asyncio
async def test_get_dau_basic():
    """Базовий сценарій — два дні статистики DAU."""
    rows = [
        (date(2025, 1, 1), 3),
        (date(2025, 1, 2), 2),
    ]
    db = FakeDB(rows=rows)
    user = DummyUser(id=1)

    result = await get_dau(
        from_date=date(2025, 1, 1),
        to_date=date(2025, 1, 2),
        segment=None,
        current_user=user,
        db=db,
    )
    assert result == {"2025-01-01": 3, "2025-01-02": 2}


@pytest.mark.asyncio
async def test_get_dau_invalid_range_400():
    """Якщо from_date > to_date — має бути 400."""
    db = FakeDB(rows=[])
    user = DummyUser(id=1)

    with pytest.raises(HTTPException) as ei:
        await get_dau(
            from_date=date(2025, 1, 3),
            to_date=date(2025, 1, 1),
            segment=None,
            current_user=user,
            db=db,
        )
    assert ei.value.status_code == 400
    assert "must be earlier than or equal" in ei.value.detail


@pytest.mark.asyncio
async def test_get_dau_segment_invalid_format_returns_400():
    """Невірний формат сегмента (без ':' або '=') — 400."""
    db = FakeDB(rows=[])
    user = DummyUser(id=1)

    with pytest.raises(HTTPException) as ei:
        await get_dau(
            from_date=date(2025, 1, 1),
            to_date=date(2025, 1, 2),
            segment="badformat",
            current_user=user,
            db=db,
        )
    assert ei.value.status_code == 400
    assert "Invalid segment format" in ei.value.detail


# ---------- Тести get_top_events ----------

@pytest.mark.asyncio
async def test_get_top_events_basic():
    """Перевірка базового запиту топ-івентів."""
    rows = [
        ("purchase", 5),
        ("signup", 2),
    ]
    db = FakeDB(rows=rows)
    user = DummyUser(id=42)

    result = await get_top_events(
        limit=10,
        current_user=user,
        db=db,
    )
    assert result == [
        {"event_type": "purchase", "count": 5},
        {"event_type": "signup", "count": 2},
    ]


# ---------- Тести get_cohort_analysis ----------

@pytest.mark.asyncio
async def test_retention_future_date_400():
    """Майбутня дата старту — помилка 400."""
    user = DummyUser(id=7)
    db = FakeDB(scalar=0)
    future = date.today() + timedelta(days=1)

    with pytest.raises(HTTPException) as ei:
        await get_cohort_analysis(
            start_date=future,
            window=4,
            current_user=user,
            db=db,
        )
    assert ei.value.status_code == 400
    assert "cannot be in the future" in ei.value.detail


@pytest.mark.asyncio
async def test_retention_zero_users_returns_message(monkeypatch):
    """Якщо немає користувачів у когорті — повертає повідомлення."""
    user = DummyUser(id=7)
    db = FakeDB(scalar=0)

    async def fake_first_visit_users(start_date):
        # Порожня підзапитна таблиця
        empty_subq = select(literal(1)).where(literal(False)).subquery()
        return empty_subq

    monkeypatch.setattr(routers_mod, "get_first_visit_users", fake_first_visit_users)

    result = await get_cohort_analysis(
        start_date=date(2025, 1, 1),
        window=4,
        current_user=user,
        db=db,
    )
    assert "details" in result
    assert "No first visit users" in result["details"]


@pytest.mark.asyncio
async def test_retention_basic_happy_path(monkeypatch):
    """Щасливий сценарій — є користувачі, є статистика по тижнях."""
    user = DummyUser(id=9)
    start = date(2025, 1, 6)
    db = FakeDB(scalar=2)  # когорти з 2 користувачів

    async def fake_first_visit_users(_start_date):
        two_rows = union_all(select(literal(1)), select(literal(1))).subquery()
        return two_rows

    async def fake_cohort_week_active_count(_first_sq, _start_date, _db, week, users_count):
        return {"active": 1, "retention": 0.5, "week": week}

    monkeypatch.setattr(routers_mod, "get_first_visit_users", fake_first_visit_users)
    monkeypatch.setattr(routers_mod, "cohort_week_active_count", fake_cohort_week_active_count)

    result = await get_cohort_analysis(
        start_date=start,
        window=3,
        current_user=user,
        db=db,
    )
    assert result["start_date"] == str(start)
    assert result["window"] == 3
    assert result["cohort_size"] == 2
    assert isinstance(result["weeks"], list) and len(result["weeks"]) == 3

    for i, week_dict in enumerate(result["weeks"]):
        assert week_dict["week_num"] == i
        assert week_dict["active"] == 1
        assert week_dict["retention"] == 0.5
