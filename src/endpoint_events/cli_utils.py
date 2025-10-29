# ./src/endpoint_events/cli_utils.py
# This module contains utility functions for CLI operations related to events.


####### IMPORT TOOLS ########
# global imports
import json, logging, asyncio, argparse, aiofiles, csv, sys
from datetime import datetime
from aiocsv import AsyncDictReader
from pydantic.dataclasses import dataclass
from typing import Dict, Any, Optional, List
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# local imports
from src.data_base.models import Events
from src.config import get_settings


####### LOGGER ########
logger = logging.getLogger("app.endpoint_events.cli_utils")


######## MAKE TABLE ########
@dataclass
class EventRow:
    event_id: str
    occurred_at: datetime
    user_id: int
    event_type: str
    properties: Dict[str, Any]


######## PARSE ROW & VALIDATE DATA ########
def parse_row(row: Dict[str, str], line_num: int) -> Optional[EventRow]:
    required_fields = ["event_id", "occurred_at", "user_id", "event_type", "properties_json"]
    missing_fields = [k for k in required_fields if k not in row or row[k] is None]
    if missing_fields:
        print(f"[WARN] Line {line_num}: missing columns: {missing_fields}")
        return None

    # event_id: UUID
    event_id = row["event_id"].strip()
    if not event_id:
        print(f"[WARN] Line {line_num}: empty event_id")
        return None

    # occurred_at: ISO-8601 with timezone (напр. 2025-08-21T06:52:34+03:00)
    try:
        occurred_at = datetime.fromisoformat(row["occurred_at"].strip())
    except Exception as e:
        print(f"[WARN] Line {line_num}: bad occurred_at '{row['occurred_at']}': {e}")
        return None

    # user_id: int
    try:
        user_id = int(row["user_id"])
    except Exception as e:
        print(f"[WARN] Line {line_num}: bad user_id '{row['user_id']}': {e}")
        return None

    # event_type: str
    event_type = row["event_type"].strip()
    if not event_type:
        print(f"[WARN] Line {line_num}: empty event_type")
        return None

    # properties_json: JSON object or text
    raw_properties = row["properties_json"]
    try:
        properties = json.loads(raw_properties) if raw_properties else {}
        # Ensure properties is a dict & save as {"value": ...} if not
        if not isinstance(properties, dict):
            properties = {"value": properties}
    except Exception as e:
        print(f"[WARN] Line {line_num}: bad properties_json '{raw_properties}': {e}")
        return None

    return EventRow(
        event_id=event_id,
        occurred_at=occurred_at,
        user_id=user_id,
        event_type=event_type,
        properties=properties,
    )


######## INSERT CURRENT BATCH TO DATABASE ########
async def insert_batch(engine: AsyncEngine, table: Events, batch: List[EventRow]) -> int:
    if not batch:
        return 0

    payload = [
        {
            "event_id": row.event_id,
            "occurred_at": row.occurred_at,
            "user_id": row.user_id,
            "event_type": row.event_type,
            "properties": row.properties,
        }
        for row in batch
    ]

    insert_statement = (
        pg_insert(table)
        .values(payload)
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(table.c.event_id)
    )

    async with engine.begin() as connection:
        result =await connection.execute(insert_statement)
        inserted_ids = [row[0] for row in result.fetchall()]
        return len(inserted_ids)


######## IMPORT CSV TO DATABASE ########
async def import_csv(csv_path: str, batch_size) -> None:
    db_url = get_settings().USER_DB_URL
    table = Events.__table__
    engine: AsyncEngine = create_async_engine(db_url, future=True, pool_pre_ping=True)

    # Counting variables
    total_read_lines = 0
    total_parsed_lines = 0
    total_inserted_lines = 0
    duplicate_lines = 0
    batch: List[EventRow] = []
    expected_head_fields = ["event_id", "occurred_at", "user_id", "event_type", "properties_json"]
    field_delimiter = ","

    try:
        # Validate CSV header
        async with aiofiles.open(csv_path, "r", encoding="utf-8-sig", newline="") as file_head:
            header_line = await file_head.readline()
            if not header_line:
                logger.error("Uploaded CSV file is empty or wrong format (even header is absent).")
                raise RuntimeError("CSV file is empty of wrong format (even header is absent).")
            header = next(csv.reader([header_line], delimiter=field_delimiter))
            header = [head.strip() for head in header]
            missing = [column for column in expected_head_fields if column not in header]
            if missing:
                logger.error("Uploaded CSV header missing columns: %s. Got: %s", missing, header)
                raise RuntimeError(
                    f"CSV header must include columns: {', '.join(expected_head_fields)}. Got: {header}"
                )

        # Read and process CSV rows
        async with aiofiles.open(csv_path, "r", encoding="utf-8-sig", newline="") as csv_file:
            await csv_file.readline()
            file_reader = AsyncDictReader(csv_file, fieldnames=header, delimiter=field_delimiter)

            line_num = 1
            async for row in file_reader:
                line_num += 1
                total_read_lines += 1
                event_row = parse_row(row, line_num)
                if event_row is None:
                    continue
                total_parsed_lines += 1
                batch.append(event_row)

                if len(batch) >= batch_size:
                    inserted_batch = await insert_batch(engine, table, batch)
                    total_inserted_lines += inserted_batch
                    duplicate_lines += len(batch) - inserted_batch
                    batch.clear()
                    print(f"[INFO] Imported {total_inserted_lines} lines from {total_read_lines} read ({total_parsed_lines} parsed). Duplicates events: {duplicate_lines}")

        # Insert any remaining rows in the last batch
        if batch:
            inserted_batch = await insert_batch(engine, table, batch)
            total_inserted_lines += inserted_batch
            duplicate_lines += len(batch) - inserted_batch
            print(f"[INFO] Last batch: Imported {total_inserted_lines} lines from {total_read_lines} read ({total_parsed_lines} parsed). Duplicates events: {duplicate_lines}")

    finally:
        await engine.dispose()

    logger.info(
        "Data uploading from CSV. Lines read: %d, parsed: %d, inserted: %d, duplicates: %d.",
        total_read_lines, total_parsed_lines, total_inserted_lines, duplicate_lines
    )
    print(
        f"[DONE] Data uploading is completed.\nLines read: {total_read_lines}, parsed: {total_parsed_lines}, inserted: {total_inserted_lines}, duplicates: {duplicate_lines}."
    )

######## MAIN FUNCTION FOR CLI ########
def main() -> None:
    logging.basicConfig(
        level = logging.INFO,
        format = "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        filename=get_settings().LOG_FILE,
        filemode="a",
    )
    parser = argparse.ArgumentParser(
        prog="import_events",
        description="Імпорт подій з CSV у базу даних.",
    )
    parser.add_argument(
        "csv_path",
        help="Шлях до CSV (event_id, occurred_at, user_id, event_type, properties_json)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Розмір партії вставки (за замовчуванням 1000)",
    )
    args = parser.parse_args()

    asyncio.run(import_csv(args.csv_path, args.batch_size))


######## ENTRY POINT ########
if __name__ == "__main__":
    main()
