# ./tests/test_endpoint_events/test_endpoint_events_cli_utils.py


###### IMPORT TOOLS ######
# global imports
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

# local imports
import src.endpoint_events.cli_utils as cli_utils


###### FAKE ASYNC ENGINE ######
class FakeAsyncEngine:
    """Minimal async engine stub with only dispose()."""
    def __init__(self, url="postgresql+asyncpg://fake/fake"):
        self.url = url
        self._disposed = False

    async def dispose(self):
        self._disposed = True


###### FIXTURES ######
@pytest.fixture
def tmp_csv(tmp_path: Path):
    """Factory to quickly create CSV files with given lines."""
    def _make(name: str, lines: list[str]) -> Path:
        p = tmp_path / name
        p.write_text("\n".join(lines), encoding="utf-8")
        return p
    return _make


@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    """Ensure get_settings().USER_DB_URL is present and stable in tests."""
    monkeypatch.setattr(
        cli_utils,
        "get_settings",
        lambda: SimpleNamespace(USER_DB_URL="postgresql+asyncpg://test/test", LOG_FILE=None),
    )


###### TESTS ######
def test_parse_row_valid_iso_and_json_dict():
    row = {
        "event_id": "11111111-1111-1111-1111-111111111111",
        "occurred_at": "2025-08-21T06:52:34+03:00",
        "user_id": "42",
        "event_type": "login",
        "properties_json": json.dumps({"ip": "1.2.3.4", "country": "UA"}),
    }
    parsed = cli_utils.parse_row(row, line_num=2)
    assert parsed is not None
    assert parsed.event_id == row["event_id"]
    assert parsed.user_id == 42
    assert parsed.event_type == "login"
    assert parsed.properties == {"ip": "1.2.3.4", "country": "UA"}


def test_parse_row_non_dict_properties_becomes_wrapped_value():
    row = {
        "event_id": "22222222-2222-2222-2222-222222222222",
        "occurred_at": "2025-08-21T06:52:34+03:00",
        "user_id": "7",
        "event_type": "purchase",
        "properties_json": json.dumps(["a", "b"]),  # list instead of dict
    }
    parsed = cli_utils.parse_row(row, line_num=3)
    assert parsed is not None
    assert parsed.properties == {"value": ["a", "b"]}


def test_parse_row_bad_occurred_at_returns_none(capsys):
    row = {
        "event_id": "33333333-3333-3333-3333-333333333333",
        "occurred_at": "not-a-timestamp",
        "user_id": "10",
        "event_type": "login",
        "properties_json": json.dumps({"ok": True}),
    }
    parsed = cli_utils.parse_row(row, line_num=5)
    assert parsed is None
    out = capsys.readouterr().out
    assert "bad occurred_at" in out


def test_parse_row_missing_required_field_returns_none(capsys):
    row = {
        # missing event_id
        "occurred_at": "2025-08-21T06:52:34+03:00",
        "user_id": "10",
        "event_type": "login",
        "properties_json": "{}",
    }
    parsed = cli_utils.parse_row(row, line_num=7)
    assert parsed is None
    out = capsys.readouterr().out
    assert "missing columns" in out or "empty event_id" in out


@pytest.mark.asyncio
async def test_insert_batch_empty_returns_zero():
    count = await cli_utils.insert_batch(engine=None, table=None, batch=[])
    assert count == 0


@pytest.mark.asyncio
async def test_import_csv_happy_path_batches_and_counts(monkeypatch, tmp_csv, capsys):
    lines = [
        "event_id,occurred_at,user_id,event_type,properties_json",
        "a1,2025-01-01T00:00:00+00:00,1,login,{}",
        "a2,2025-01-01T00:00:01+00:00,2,logout,{\"k\":1}",
        "a3,2025-01-01T00:00:02+00:00,3,login,{\"k\":2}",
    ]
    csv_path = tmp_csv("ok.csv", lines)
    fake_engine = FakeAsyncEngine()
    monkeypatch.setattr(cli_utils, "create_async_engine", lambda *a, **k: fake_engine)
    calls = []
    async def _fake_insert(engine, table, batch):
        calls.append([row.event_id for row in batch])
        return len(batch)

    monkeypatch.setattr(cli_utils, "insert_batch", _fake_insert)
    await cli_utils.import_csv(str(csv_path), batch_size=2)
    assert calls == [["a1", "a2"], ["a3"]]
    out = capsys.readouterr().out
    assert "[DONE] Data uploading is completed." in out
    assert "Lines read: 3, parsed: 3, inserted: 3, duplicates: 0" in out
    assert fake_engine._disposed is True


@pytest.mark.asyncio
async def test_import_csv_counts_duplicates(monkeypatch, tmp_csv, capsys):
    lines = [
        "event_id,occurred_at,user_id,event_type,properties_json",
        "d1,2025-01-01T00:00:00+00:00,1,login,{}",
        "d2,2025-01-01T00:00:00+00:00,1,login,{}",
        "d3,2025-01-01T00:00:00+00:00,1,login,{}",
    ]
    csv_path = tmp_csv("dups.csv", lines)
    monkeypatch.setattr(cli_utils, "create_async_engine", lambda *a, **k: FakeAsyncEngine())
    results = [1, 1]
    async def _fake_insert(engine, table, batch):
        return results.pop(0)

    monkeypatch.setattr(cli_utils, "insert_batch", _fake_insert)
    await cli_utils.import_csv(str(csv_path), batch_size=2)
    out = capsys.readouterr().out
    assert "inserted: 2, duplicates: 1" in out


@pytest.mark.asyncio
async def test_import_csv_missing_required_header_raises(monkeypatch, tmp_csv):
    lines = [
        "event_id,occurred_at,user_id,event_type",
        "x1,2025-01-01T00:00:00+00:00,1,login",
    ]
    csv_path = tmp_csv("bad_header.csv", lines)
    monkeypatch.setattr(cli_utils, "create_async_engine", lambda *a, **k: FakeAsyncEngine())
    with pytest.raises(RuntimeError) as exc:
        await cli_utils.import_csv(str(csv_path), batch_size=100)
    assert "CSV header must include columns" in str(exc.value)


@pytest.mark.asyncio
async def test_import_csv_empty_file_raises(monkeypatch, tmp_csv):
    csv_path = tmp_csv("empty.csv", [])
    monkeypatch.setattr(cli_utils, "create_async_engine", lambda *a, **k: FakeAsyncEngine())
    with pytest.raises(RuntimeError) as exc:
        await cli_utils.import_csv(str(csv_path), batch_size=100)
    assert "CSV file is empty" in str(exc.value)


def test_main_parses_args_and_runs(monkeypatch, tmp_csv):
    lines = [
        "event_id,occurred_at,user_id,event_type,properties_json",
        "m1,2025-01-01T00:00:00+00:00,1,login,{}",
    ]
    csv_path = tmp_csv("cli.csv", lines)
    called = {"args": None}
    async def spy_import_csv(csv_arg: str, batch_arg: int):
        called["args"] = (csv_arg, batch_arg)
    monkeypatch.setattr(cli_utils, "import_csv", spy_import_csv)
    argv_backup = sys.argv[:]
    sys.argv = ["import_events", str(csv_path), "--batch-size", "123"]
    try:
        cli_utils.main()
    finally:
        sys.argv = argv_backup
    assert called["args"] is not None, "import_csv was not invoked"
    got_csv, got_batch = called["args"]
    assert got_csv == str(csv_path)
    assert got_batch == 123
