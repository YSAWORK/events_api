# Events
Це сервіс на **FastAPI** для інґесту подій (events) та розрахунку базової продукт‑аналітики (DAU, ТОП-івенти, когорти/ретеншн). Проєкт містить **авторизацію з JWT**, **PostgreSQL** (async SQLAlchemy), **Redis** (кеш токенів та rate‑limit), **Alembic** міграції, **Prometheus** метрики, CLI для **CSV‑імпорту** та **бенчмарк** на імпорт з CSV файлу 100k подій та підрахунку DAU.

## Основні можливості
- **Імпорт і запис подій** у таблицю `events` з upsert‑логікою (уникнення дублікатів по `event_id`).
- **API статистики**:
  - `DAU` за діапазон дат.
  - Фільтр ТОП-подій за кількістю.
  - Когортний аналіз/ретеншн по тижнях.
- **Користувачі та автентифікація**: реєстрація/логін, оновлення токенів, інвалідація refresh‑сесій (Redis).
- **Тротлінг** запитів через `fastapi-limiter` (Redis).
- **Метрики** Prometheus: HTTP, бізнес‑події, інфлайт‑джоби.
- **Бенчмарк**: 
  - імпорт 100k подій з CSV файлу базу даних, запит DAU, вимір часу.
- **Docker Compose** для локального запуску (API + Postgres + Redis + job для міграцій).
- **Alembic** міграції під async SQLAlchemy.

---

## Технічний стек
- Python 3.12, FastAPI, Pydantic v2
- SQLAlchemy async + Alembic
- PostgreSQL, asyncpg / psycopg2 (admin)
- Redis (token cache, rate limit)
- prometheus‑fastapi‑instrumentator, prometheus_client
- httpx/requests, aiocsv/aiofiles (CSV)
- pytest / pytest‑asyncio

---

## Структура проєкту
```
robomate_take_home/
├─ docker-compose.yml
├─ Makefile
├─ alembic.ini
├─ migrations/
│  ├─ env.py
│  └─ versions/
├─ src/
│  ├─ main.py                    # FastAPI app, lifespan (resources, rate-limit)
│  ├─ routers.py                 # Головний APIRouter
│  ├─ config.py                  # Settings (DB, Redis, CORS, тощо)
│  ├─ data_base/
│  │  ├─ db.py                   # Async engine, session, Base
│  │  ├─ models.py               # User, Events
│  │  └─ crud.py                 # Auth + Benchmark user
│  ├─ endpoint_events/
│  │  ├─ routers.py              # POST /events, вставка пачки з upsert
│  │  ├─ schemas.py              # Pydantic схеми Event/EventsIn/EventsOut
│  │  └─ cli_utils.py            # CLI імпорт CSV
│  ├─ endpoint_stats/
│  │  ├─ schemas.py              # Pydantic схеми 
│  │  ├─ routers.py              # GET /stats/dau, GET /stats/top-events, GET /stats/retention
│  │  └─ utils.py                # Обчислення когорти/ретеншну
│  ├─ user_auth/
│  │  ├─ routers.py              # /auth: register/login/refresh/logout/change-password
│  │  ├─ schemas.py              # Pydantic схеми UserIn/UserOut/AuthTokens
│  │  └─ utils.py                # хешування, JWT, валідація токенів
│  ├─ infrastructure/
│  │  ├─ resources.py            # Redis, rate-limiter, session factory
│  │  ├─ cache.py                # TokenCache для refresh токенів
│  │  └─ metrics.py              # трекер бізнес‑подій
│  ├─ metrics/                   # Prometheus метрики та інтеграція
│  │  ├─ app_metrics.py          # Бізнес‑метрики
│  │  └─ setup.py                # Ініцsалізація інструментатора
│  ├─ logs/                      # Логування + кастомні хендлери
│  ├─ security/                  # Хешування паролів, JWT
│  └─ benchmarks/                # Бенчмарк 100k подій
│     ├─ dau_100k/
│     │  └─ generate_events.py   # Генератор подій
│     └─ run_benchmarks.py       # Імпорт + запит DAU +
└─ tests                         # Тести
```

> **Базовий шлях API** визначається `get_settings().API_PREFIX` (типово — `"/api"`), далі модульні префікси: `/auth`, `/events`, `/stats`.

---

## Швидкий старт (локально, без Docker)
1. Створіть та активуйте віртуальне середовище, встановіть залежності.
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows
pip install -r docer_dir/requirements.txt
```
2. Створіть та заповніть `.env.prod`.
3. Створіть БД та застосуйте міграції.
4. Запустіть API.

Приклад змінних (див. `src/config.py`):
```
APP_ENV=dev
API_HOST=0.0.0.0
API_PORT=8002

# Postgres (async для додатку)
USER_DB_URL=postgresql+asyncpg://user:pass@localhost:5432/dbname
# Admin URL (sync) для Alembic/скриптів
POSTGRES_ALEMBIC_URL=postgresql+psycopg2://user:pass@localhost:5432/dbname
DB_ADMIN_URL=postgresql+psycopg2://postgres@/postgres?host=/var/run/postgresql

# Redis
REDIS_URL=redis://localhost:6379/0
TOKEN_CACHE_PREFIX=fapi-tokens

# CORS
CORS_ORIGINS=*
# або JSON-рядок: ["http://localhost:5173","https://example.com"]

# Токени
SECRET_KEY=change-me
ACCESS_TTL_MIN=15
REFRESH_TTL_DAYS=7

# Бенчмарк
BENCHMARK_TOKEN=TEST_TOKEN_VALUE
```

**Міграції:**
```bash
alembic upgrade head
alembic revision -m "message"  # за потреби
```

**Запуск API:**
```bash
python -m src.main
# або через uvicorn:
uvicorn src.main:app --host 0.0.0.0 --port 8002 --reload
```

---

## Запуск через Docker Compose
> Порти/імена контейнерів див. у `docker-compose.yml`.

```bash
# використати .env.prod як джерело змінних
docker compose --env-file .env.prod up --build
```

Сервіси:
- **api** — FastAPI.
- **db** — PostgreSQL (є healthcheck, порт може бути проброшений як `55432:5432`).
- **redis** — для кешу токенів/лімітера.
- **migrate** — одноразовий контейнер, що виконує `alembic upgrade head` перед стартом `api`.

---

## Makefile (корисні цілі)
```bash
make help

# Імпорт подій з CSV
make import_events path/to.csv

# Запуск API локально
make run_api

# Бенчмарк (повний модуль)
make benchmark

# Лише функція test_100k_dau()
make benchmark_func
```

---

## Імпорт CSV подій (CLI)
Модуль: `src/endpoint_events/cli_utils.py`

Параметри:
- шлях до CSV,
- розмір батчу (за замовчуванням розумний, див. CLI).

Формат CSV очікується з полями на кшталт:
```
event_id,occurred_at,user_id,event_type,properties
550e8400-e29b-41d4-a716-446655440000,2025-08-01T12:34:56Z,123,login,"{}"
...
```

Команда:
```bash
make import_events data/events.csv
# або
PYTHONPATH=. python -m src.endpoint_events.cli_utils --csv data/events.csv --batch-size 5000
```

**Upsert**: вставка виконується через `INSERT ... ON CONFLICT DO NOTHING` по `event_id`, дублі пропускаються, у відповіді/логах — кількість вставлених і дублікатів.

---

## API

### Авторизація (`/auth`)
Типові ручки (див. `src/user_auth/routers.py`):
- `POST /auth/register` — створення користувача.
- `POST /auth/login` — отримання `access`/`refresh` токенів.
- `POST /auth/refresh` — оновлення токенів.
- `POST /auth/logout` — інвалідація refresh‑сесії.
- `POST /auth/change-password` — зміна пароля (анулює всі refresh токени користувача).
- Валідація токенів, перевірка відкликаних токенів в **Redis** (`TokenCache`).

### Події (`/events`)
- `POST /events` — приймає `EventsIn`:
```json
[ 
    {
      "event_id": "uuid",
      "occurred_at": "2025-08-01T00:00:00Z",
      "user_id": 123,
      "event_type": "login",
      "properties": {}
    }
]
```
Відповідь: `EventsOut` з масивами `inserted` та `duplicates`.

> На ендпоінт повішений rate‑limit через `fastapi-limiter`.

### Статистика (`/stats`)
- `GET /stats/dau?from=YYYY-MM-DD&to=YYYY-MM-DD` — повертає список `{{"day": "...","dau": N}}`.
- `GET /stats/cohort?start_date=YYYY-MM-DD&window=8` — тижневий ретеншн від дати першого візиту (cohort size + % активних по кожному тижню).
- `GET /stats/top-events?from=YYYY-MM-DD&to=YYYY-MM-DD&limit=N` — топ N подій за кількістю.

> Для бенчмарку реалізовано "benchmark user": якщо запит позначений middleware як бенчмарк‑режим, авторизація спрощується (див. `src/data_base/crud.py` — `benchmark_or_auth`).

---

## Метрики
- HTTP‑метрики: `prometheus-fastapi-instrumentator`.
- Бізнес‑метрики (приклади у `src/metrics/app_metrics.py`):
  - `events_total{{source}}` — кількість оброблених подій,
  - `event_processing_seconds` — гістограма часу обробки,
  - `inflight_jobs` — gauge поточних задач.
- Ініціалізація та лейбли додатку — у `src/metrics/setup.py`.
- Додатковий хелпер `src/infrastructure/metrics.py` для реєстрації подій з коду.

Експозиція — стандартний `/metrics` (додається інструментатором).

---

## Rate‑limit та CORS
- **Rate‑limit**: `fastapi-limiter` з Redis, ініціалізується в `src/main.py` в lifespan.
- **CORS**: список хостів у `CORS_ORIGINS`. Якщо `allow_credentials=True` — `"*"` буде відфільтровано (див. додавання middleware у `main.py`).

---

## Тести
- `pytest`, `pytest-asyncio` (режим `asyncio_mode=auto` у `pytest.ini`).
- Фікстури для підняття застосунку, клієнта, сесій БД — у `conftest.py`.
- Покриття: `coverage run -m pytest` → `coverage html`.

---

## Бенчмарк 
Модуль: `src/benchmarks/run_benchmarks.py` (масштабується під інші тести).
### test_100k_dau
Генератор `src/benchmarks/dau_100k/generate_events.py`.

Що робить:
1) генерує 100k подій (рівномірно розкладених у часі),  
2) імпортує в тестову БД (Postgres, під час тесту створюється, по закінченню видаляється),
3) викликає `GET /stats/dau` в діапазоні та перевіряє відповідь,

Запуск:
```bash
make benchmark                                # весь модуль (__main__)
make benchmark_func FUNK=<назва бенчмарку>    # наприклад test_100k_dau
```

### Вузькі місця:
- Імпорт здійснюється поетапно (див. `src/benchmarks/dau_100k/generate_events.py`) : 1000 рядків за один цикл, щоб уникнути overhead від журналювання великої кількості рядків.
- Для чистоти вимірювання використовується тестова БД аналогічна реальній (див. `create_test_database` в `src/benchmarks/run_benchmarcks.py` та тестове оточення `.env.test`, щоб не впливали інші дані та отримання реальних метрик.
- Для обходу автентифікації використовується спрощений механізм (див. `benchmark_or_auth` у `src/data_base/crud.py`).

---

## Міграції БД (Alembic)
- Файл `migrations/env.py` налаштований на **async**‑двигун.
- Початкова ревізія: `fd8bb983322f_initial` (створює `users`, `events`, індекси).
- Команди:
```bash
alembic upgrade head
alembic downgrade -1
```
