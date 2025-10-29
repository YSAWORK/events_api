# ./tests/test_benchmarcks/test_generate_events.py


######## IMPORT TOOLS ########
import csv
import json
import re
import runpy
from datetime import datetime, timedelta
from pathlib import Path


##### TESTS ######
def test_generate_csv_creates_file(tmp_path: Path):
    """
    Execute a patched copy of the generator so that:
      - BASE_DIR -> tmp_path
      - n -> 10
      - timedelta_min -> 60 (1 hour) to keep parsing quick
    Then validate the CSV structure and values.
    """
    original = Path("src/benchmarks/dau_100k/generate_events.py")
    assert original.exists(), f"Script not found: {original}"
    src = original.read_text(encoding="utf-8")

    # 1) Replace `from src.config import BASE_DIR` with a literal BASE_DIR pointing to tmp_path
    src = re.sub(
        r"from\s+src\.config\s+import\s+BASE_DIR",
        f"BASE_DIR = r\"{tmp_path.as_posix()}\"",
        src,
        count=1,
    )
    # 2) Reduce n from 100_000 to 10
    src = re.sub(r"\bn\s*=\s*100_000\b", "n = 10", src, count=1)
    # 3) Reduce timedelta_min to keep range small
    src = re.sub(r"\btimedelta_min\s*=\s*60\*24\*30\b", "timedelta_min = 60", src, count=1)

    # Write patched copy
    patched = tmp_path / "generate_events_patched.py"
    patched.write_text(src, encoding="utf-8")

    # Ensure output dir exists (script will also create it via open with parent dirs already created)
    out_csv = tmp_path / "src" / "benchmarks" / "dau_100k" / "test_csv.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    # Run the patched script (executes top-level code)
    runpy.run_path(str(patched), run_name="__main__")

    # ---- Assertions ----
    assert out_csv.exists(), f"CSV was not created at {out_csv}"

    rows = list(csv.reader(out_csv.open("r", encoding="utf-8", newline="")))
    assert rows, "CSV must not be empty"
    header = rows[0]
    assert header == ["event_id", "occurred_at", "user_id", "event_type", "properties_json"]

    data = rows[1:]
    assert len(data) == 10, "Should generate 10 data rows"

    # Get the same constants the script used after patch
    start_day = datetime(2025, 8, 1)
    end_day = start_day + timedelta(minutes=60)  # patched timedelta_min

    for row in data:
        assert len(row) == 5, "Each row must have 5 columns"
        event_id, occurred_at, user_id, event_type, props = row

        # UUID format (simple check)
        assert event_id.count("-") == 4, f"Invalid UUID: {event_id}"

        # occurred_at must be ISO8601 within the window
        dt = datetime.fromisoformat(occurred_at)
        assert start_day <= dt <= end_day, "occurred_at outside expected range"

        # user_id in [1, 1000]
        uid = int(user_id)
        assert 1 <= uid <= 1000, "user_id must be within [1, 1000]"

        # event_type among allowed
        assert event_type in {"app_open", "login", "view_item", "purchase"}

        # properties_json valid JSON with country=UA
        obj = json.loads(props)
        assert isinstance(obj, dict)
        assert obj.get("country") == "UA"


def test_generate_csv_overwrites_file(tmp_path: Path):
    """Running patched script twice should overwrite (not append) the CSV."""
    original = Path("src/benchmarks/dau_100k/generate_events.py")
    src = original.read_text(encoding="utf-8")
    src = re.sub(r"from\s+src\.config\s+import\s+BASE_DIR", f"BASE_DIR = r\"{tmp_path.as_posix()}\"", src, count=1)
    src = re.sub(r"\bn\s*=\s*100_000\b", "n = 3", src, count=1)
    src = re.sub(r"\btimedelta_min\s*=\s*60\*24\*30\b", "timedelta_min = 60", src, count=1)

    patched = tmp_path / "generate_events_patched.py"
    patched.write_text(src, encoding="utf-8")

    out_csv = tmp_path / "src" / "benchmarks" / "dau_100k" / "test_csv.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    # First run
    runpy.run_path(str(patched), run_name="__main__")
    first_rows = list(csv.reader(out_csv.open("r", encoding="utf-8", newline="")))
    assert len(first_rows) == 1 + 3, "Header + 3 rows expected after first run"

    # Write junk to ensure overwrite actually happens
    out_csv.write_text("junk\n", encoding="utf-8")

    # Second run should overwrite
    runpy.run_path(str(patched), run_name="__main__")
    second_rows = list(csv.reader(out_csv.open("r", encoding="utf-8", newline="")))
    assert len(second_rows) == 1 + 3, "Header + 3 rows expected after second run (overwrite)"
