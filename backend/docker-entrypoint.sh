#!/usr/bin/env bash
set -e

# wait for Postgres
until pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-postgres}"; do
  sleep 1
done

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  alembic upgrade head
fi

# If args provided, run them; otherwise start uvicorn
if [ "$#" -gt 0 ]; then
  exec "$@"
else
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi