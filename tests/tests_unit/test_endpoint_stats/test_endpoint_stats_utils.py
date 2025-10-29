# tests/test_endpoint_stats/test_endpoint_stats_utils.py


###### IMPORT TOOLS ######
# global imports
import pytest
from datetime import date
from types import SimpleNamespace
from sqlalchemy import Table, Column, Integer, MetaData
from sqlalchemy.sql.selectable import Select


####### TESTS FOR ENDPOINT STATS UTILITIES ########
@pytest.mark.asyncio
async def test_get_first_visit_users_builds_expected_select(monkeypatch):
    """Test that get_first_visit_users constructs the expected SQL SELECT statement."""
    import src.endpoint_stats.utils as utils
    monkeypatch.setattr(utils, "get_settings", lambda: SimpleNamespace(TIMEZONE="UTC"))
    target_day = date(2025, 8, 1)
    stmt = await utils.get_first_visit_users(target_day)
    assert isinstance(stmt, Select)
    sel_cols = list(stmt.selected_columns)
    assert any(getattr(c, "name", "") == "user_id" for c in sel_cols)
    gb_cols = list(stmt._group_by_clauses)
    assert any(getattr(c, "name", "") == "user_id" for c in gb_cols)
    assert getattr(stmt, "_having_criteria", None), "HAVING має бути заданий"


@pytest.mark.asyncio
async def test_cohort_week_active_count_happy_path(monkeypatch):
    """Test cohort_week_active_count returns correct counts and percentages."""
    import src.endpoint_stats.utils as utils
    monkeypatch.setattr(utils, "get_settings", lambda: SimpleNamespace(TIMEZONE="UTC"))
    md = MetaData()
    users_tbl = Table("tmp_users", md, Column("user_id", Integer, primary_key=True))
    class _ExecResult:
        def __init__(self, value):
            self._value = value
        def scalar_one(self):
            return self._value

    class DummySession:
        def __init__(self, value):
            self._value = value
        async def execute(self, stmt):
            str(stmt)
            return _ExecResult(self._value)

    start = date(2025, 1, 1)
    week_num = 0
    users_count = 20
    expected_count = 7
    session = DummySession(expected_count)

    result = await utils.cohort_week_active_count(
        users=users_tbl,
        start_date=start,
        database_session=session,
        week_num=week_num,
        users_count=users_count,
    )
    assert result["week_active_users"] == expected_count
    assert result["percent"] == 35.0  # 7 / 20 * 100
    assert result["period"] == "2025-01-02 - 2025-01-08"
