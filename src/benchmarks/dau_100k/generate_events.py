# .src/benchmarks/dau_100k/generate_events.py
# This script generates a CSV file with 100,000 synthetic event records for testing purposes.


###### IMPORT TOOLS ######
# global imports
import csv, random, uuid
from datetime import datetime, timedelta

# local imports
from src.config import BASE_DIR


n = 100_000
start_day = datetime(2025, 8, 1)
timedelta_min = 60*24*30
events = ["app_open", "login", "view_item", "purchase"]

with open(f"{BASE_DIR}/src/benchmarks/dau_100k/test_csv.csv", "w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(["event_id", "occurred_at", "user_id", "event_type", "properties_json"])
    for i in range(n):
        occurred_at = start_day + timedelta(minutes=random.randint(0, timedelta_min))
        writer.writerow([
            uuid.uuid4(),
            occurred_at.isoformat(),
            random.randint(1, 1000),
            random.choice(events),
            '{"country": "UA"}'
        ])
