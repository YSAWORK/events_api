# ./docker_dir/Dockerfile
# Dockerfile for FastAPI application
# To build: docker compose --env-file .env.(dev or prod) build
# To run: docker compose --env-file .env.(dev or prod) up


# Base image
FROM python:3.12-slim

# Prevents Python from writing pyc files to disc
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# System deps
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
    build-essential curl netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# Create user
ARG UID=1000
ARG GID=1000
RUN groupadd -g "${GID}" app || true && \
    useradd -m -u "${UID}" -g "${GID}" -s /bin/bash app

# Expose the port the app runs on
EXPOSE 8002

# Set work directory
WORKDIR /app

# Python deps
COPY ./docker_dir/requirements.txt /app/docker_dir/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r /app/docker_dir/requirements.txt uvicorn[standard]

# App
COPY --chown=app:app . /app/

# Rights and scripts
COPY docker_dir/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY docker_dir/wait-for-db.sh /usr/local/bin/wait-for-db.sh
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/wait-for-db.sh

# Change to the app user
USER root
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*
USER app
WORKDIR /app

# Run the application
CMD ["/usr/local/bin/entrypoint.sh"]
