#!/usr/bin/env sh
# Wait for the PostgreSQL database to be ready

# Exit immediately if a command exits with a non-zero status
set -e

# Check if pg_isready is available
HOST="${1:-${POSTGRES_HOST:-postgres}}"
PORT="${2:-${POSTGRES_PORT:-5432}}"
DB="${POSTGRES_DB:-${POSTGRES_DB:-postgres}}"
USER="${POSTGRES_USER:-postgres}"

# Wait for Postgres to be ready
echo "Waiting for Postgres at $HOST:$PORT (db=$DB)..."
for i in $(seq 1 30); do
  if pg_isready -h "$HOST" -p "$PORT" -U "$USER" >/dev/null 2>&1; then
    echo "Postgres is ready"
    break
  fi
  echo "[$i/30] Postgres not ready yet..."
  sleep 2
done

# If Postgres is not ready after 30 attempts, exit with an error
shift 2 || true
if [ "$#" -gt 0 ]; then
  exec "$@"
fi
