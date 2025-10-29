#!/usr/bin/env bash
# Entrypoint script for the Docker container

# Exit immediately if a command exits with a non-zero status, if an undefined variable is used, or if any command in a pipeline fails
set -euo pipefail

# Wait for the database to be ready and then start the FastAPI application
/usr/local/bin/wait-for-db.sh "${POSTGRES_HOST:-db}" "${POSTGRES_PORT:-5432}" \
  uvicorn src.main:app --host 0.0.0.0 --port 8002
