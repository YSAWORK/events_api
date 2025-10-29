# ./tests/test_benchmarcks/test_run_benchmarcks.py

####### IMPORT TOOLS ######
# global imports
from datetime import datetime
from types import SimpleNamespace

# local imports
import src.benchmarks.run_benchmarcks as mod


def test_benchmark_100k_dau(monkeypatch):
    """Test the 100k DAU benchmark function with mocked dependencies."""
    # ---------- ENV ----------
    monkeypatch.setenv("USER_DB_URL", "postgresql+asyncpg://test_user:test_pwd@localhost:5432/test_db")
    monkeypatch.setenv("DB_ADMIN_URL", "postgresql+psycopg2://postgres:admin@127.0.0.1:5432/postgres")
    monkeypatch.setenv("BENCHMARK_TOKEN", "TEST_TOKEN_VALUE")
    # ---------- Fake settings ----------
    fake_settings = SimpleNamespace(API_HOST="0.0.0.0", API_PORT=8002, BENCHMARK_TOKEN="TEST_TOKEN_VALUE")
    monkeypatch.setattr(mod, "get_settings", lambda: fake_settings)
    # ---------- Stable start_day / timedelta_min ----------
    monkeypatch.setattr(mod, "start_day", datetime(2025, 1, 1, 8, 0, 0))
    monkeypatch.setattr(mod, "timedelta_min", 180)
    # ---------- Mock subprocess.run ----------
    calls = []

    class _FakeCompleted:
        def __init__(self):
            self.returncode = 0
            self.stdout = ""
            self.stderr = ""

    def fake_run(argv, check=False):
        calls.append(list(argv))
        return _FakeCompleted()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    # ---------- Mock requests.get ----------
    req_calls = []

    class _FakeResp:
        def __init__(self, status_code=200):
            self.status_code = status_code

        def raise_for_status(self):
            if not (200 <= self.status_code < 300):
                raise RuntimeError(f"HTTP {self.status_code}")

    def fake_requests_get(url, *args, **kwargs):
        req_calls.append((url, kwargs))
        return _FakeResp(200)

    monkeypatch.setattr(mod.requests, "get", fake_requests_get)

    # ---------- Stub _wait_for_api ----------
    def fake_wait_for_api(base_url: str, timeout_sec: int = 30):
        """Fake wait_for_api that just does a quick request to /docs."""
        mod.requests.get(f"{base_url}/docs", timeout=0.01)
        return None

    monkeypatch.setattr(mod, "_wait_for_api", fake_wait_for_api)
    monkeypatch.setattr(mod.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "create_test_database", lambda *_a, **_k: None)

    # ---------- Run ----------
    mod.test_100k_dau()

    # ---------- Assertions ----------
    # subprocess calls
    assert any(cmd[:3] == ["alembic", "upgrade", "head"] for cmd in calls)
    assert any(cmd[:3] == ["python", "-m", "src.endpoint_events.cli_utils"] for cmd in calls)

    # requests calls
    docs_calls = [c for c in req_calls if c[0].endswith("/docs")]
    dau_calls = [c for c in req_calls if c[0].endswith("/stats/dau")]
    assert len(docs_calls) >= 1, "Must hit /docs at least once via _wait_for_api stub"
    assert len(dau_calls) == 1, "Must hit /stats/dau exactly once"

    # Base URL normalized
    base = "http://127.0.0.1:8002"
    assert docs_calls[0][0].startswith(base)
    assert dau_calls[0][0].startswith(base)

    # Headers and params in DAU request
    dau_kwargs = dau_calls[0][1]
    assert dau_kwargs["headers"]["Authorization"] == "Bearer TEST_TOKEN_VALUE"
    assert dau_kwargs["params"]["from"] == "2025-01-01"
    assert dau_kwargs["params"]["to"] == "2025-01-01"
