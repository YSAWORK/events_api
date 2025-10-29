# ./src/benchmarks/run_benchmarks.py
# This script benchmarks the import time of 100,000 endpoint_events and the response time for querying Daily Active Users (DAU) statistics.
# TO RUN ALL: python -m src.benchmarks.run_test


####### IMPORT TOOLS ######
# global imports
import os, time, requests, subprocess
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, make_url

# local imports
ENV_PATH = Path(__file__).resolve().parents[2] / ".env.test"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH, override=True)
from src.config import BASE_DIR, get_settings
from src.benchmarks.dau_100k.generate_events import start_day, timedelta_min


######## HELPER FUNCTIONS ######
# Resolve client host for requests
def _resolve_client_host(host: str) -> str:
    """Convert wildcard host to localhost for client requests."""
    return "127.0.0.1" if host in ("0.0.0.0", "::") else host

# Wait for API to be ready
def _wait_for_api(base_url: str, timeout_sec: int = 30) -> None:
    """Wait until the API at base_url is reachable or timeout occurs."""
    deadline = time.time() + timeout_sec
    last_err = None
    url = f"{base_url}/docs"
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code in (200, 401, 403):
                return
        except Exception as e:
            last_err = e
        time.sleep(0.5)
    raise ConnectionError(f"API at {url} not reachable within {timeout_sec} seconds.") from last_err

# Ensure database exists
def create_test_database(async_url: str):
    # Parse sync URL from async URL
    sync_url = (
        async_url
        .replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        .replace("postgresql+psycopg://", "postgresql+psycopg2://")
        .replace("postgresql://", "postgresql+psycopg2://")
    )

    # Get admin URL from environment variable
    admin_url = os.getenv("DB_ADMIN_URL")
    if not admin_url:
        raise RuntimeError("DB_ADMIN_URL not set")

    # Parse database name and user from sync URL
    u = make_url(sync_url)
    dbname = u.database
    app_user = u.username

    # Create DB if not exists, set owner and basic privileges
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": dbname}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{dbname}" OWNER "{app_user}"'))
        else:
            try:
                conn.execute(text(f'ALTER DATABASE "{dbname}" OWNER TO "{app_user}"'))
            except Exception:
                pass
        try:
            conn.execute(text(f'GRANT CONNECT, TEMP ON DATABASE "{dbname}" TO "{app_user}"'))
        except Exception:
            pass

    # Set schema owner and privileges
    admin_db_url = str(make_url(admin_url).set(database=dbname))
    print(f"[ensure_database_exists] admin_url={admin_url}")
    print(f"[ensure_database_exists] target admin_db_url={admin_db_url}")
    admin_db_engine = create_engine(admin_db_url, isolation_level="AUTOCOMMIT")
    with admin_db_engine.connect() as conn:
        try:
            conn.execute(text(f'ALTER SCHEMA public OWNER TO "{app_user}"'))
        except Exception:
            pass
        conn.execute(text(f'GRANT USAGE, CREATE ON SCHEMA public TO "{app_user}"'))
        try:
            conn.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "{app_user}"'))
            conn.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO "{app_user}"'))
        except Exception:
            pass


####### TEST FUNCTION ######
# Test importing 100,000 events and querying DAU stats
def test_100k_dau():
    """Benchmark importing 100,000 events and querying DAU statistics."""

    print(os.getenv("USER_DB_URL"), os.getenv("DB_ADMIN_URL"), os.getenv("BENCHMARK_TOKEN"))

    create_test_database(os.environ["USER_DB_URL"])
    os.environ["POSTGRES_ALEMBIC_URL"] = (
        os.environ["USER_DB_URL"]
        .replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        .replace("postgresql+psycopg://", "postgresql+psycopg2://")
        .replace("postgresql://", "postgresql+psycopg2://")
    )
    subprocess.run(["alembic", "upgrade", "head"], check=True)

    # Import events from CSV
    start = time.time()
    try:
        subprocess.run(["python","-m","src.endpoint_events.cli_utils", f"{BASE_DIR}/src/benchmarks/dau_100k/test_csv.csv"], check=True)
    except subprocess.CalledProcessError as e:
        print("CSV import failed.")
        print("STDOUT:\n", e.stdout)
        print("STDERR:\n", e.stderr)
        raise
    import_time = time.time() - start

    # prepare for DAU request
    host = _resolve_client_host(get_settings().API_HOST)
    base = f"http://{host}:{get_settings().API_PORT}"

    # wait for api to be ready
    _wait_for_api(base, timeout_sec=30)

    headers = {}
    if getattr(get_settings(), "BENCHMARK_TOKEN", None):
        headers["Authorization"] = f"Bearer {get_settings().BENCHMARK_TOKEN}"

    start_date = start_day.date().isoformat()
    end_date = (start_day + timedelta(minutes=timedelta_min)).date().isoformat()

    # make DAU request
    resp_start = time.time()
    r = requests.get(
        f"{base}/stats/dau",
        params={"from": start_date, "to": end_date},
        headers=headers,
        timeout=60,
    )
    r.raise_for_status()
    resp_time = time.time() - resp_start

    print("\n----- 100,000 EVENTS IMPORT & DAU QUERY BENCHMARK -----")
    print("------------------ test_100k_dau() --------------------")
    print("Status code:", r.status_code)
    print(f"Import time: {import_time:.2f}s")
    print(f"DAU query: {resp_time:.2f}s")


##### MAIN EXECUTION ######
if __name__ == "__main__":
    test_100k_dau()
