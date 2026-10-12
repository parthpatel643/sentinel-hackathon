#!/usr/bin/env bash
# Start the central database again from nothing: schema, one admin login,
# no detections, alerts, watchlists, cameras or audit history.
#
# For a clean demonstration, and for the post-event reset (docs/10-FINALE-
# RUNBOOK.md §10). The database is backed up to var/backups/ first, so a
# reset is never the only copy:
#
#     docker exec -i sentinel-postgres pg_restore -U sentinel -d <new db> < var/backups/<file>.dump
#
# Usage:  make reset-db CONFIRM=yes            (stop the API and every worker first)
#         make reset-db CONFIRM=yes MIRROR=1   (then `make api` and register the 30 mirrored cameras)
#
# Run the test suite against a different database: it writes test users and
# audit entries to whichever database the API uses, and audit entries cannot
# be removed without breaking the hash chain.
set -euo pipefail

CONTAINER=${SENTINEL_PG_CONTAINER:-sentinel-postgres}
PGUSER=${SENTINEL_DB_USER:-sentinel}
DB=${SENTINEL_DB_NAME:-sentinel}
INIT_DIR=infra/compose/init

if [[ "${CONFIRM:-}" != "yes" ]]; then
  echo "This deletes everything in the '$DB' database (after backing it up)."
  echo "Run again with CONFIRM=yes."
  exit 1
fi

if pgrep -f "edge_agent.worker" >/dev/null; then
  echo "An edge worker is running; stop it first (kill <pid>, it releases its relay paths)." >&2
  pgrep -fl "edge_agent.worker" >&2
  exit 1
fi
if lsof -nP -iTCP:18000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "The core API is running on :18000; stop it first." >&2
  exit 1
fi

sql() { docker exec -i "$CONTAINER" psql -U "$PGUSER" -v ON_ERROR_STOP=1 -qAt "$@"; }

mkdir -p var/backups
backup="var/backups/$DB-$(date +%Y%m%d-%H%M%S).dump"
echo "== backing up $DB to $backup"
docker exec "$CONTAINER" pg_dump -U "$PGUSER" -Fc "$DB" > "$backup" 2> >(grep -v -e circular -e 'hint:' -e 'detail:' >&2)

echo "== recreating $DB"
sql -d postgres -c "drop database if exists \"$DB\" with (force)"
sql -d postgres -c "create database \"$DB\" owner \"$PGUSER\""
for file in "$INIT_DIR"/*.sql; do
  sql -d "$DB" < "$file"
done

echo "== schema"
(cd services/core_api && uv run --project ../.. alembic upgrade head 2>&1 | tail -1)

echo "== admin login"
uv run --package core_api python scripts/seed_admin_user.py

if [[ "${MIRROR:-}" == "1" ]]; then
  echo "== mirrored cameras (starting the API briefly)"
  uv run --package core_api uvicorn core_api.app:app --port 18000 --log-level warning &
  api=$!
  trap 'kill $api 2>/dev/null || true' EXIT
  for _ in $(seq 1 60); do
    curl -sf localhost:18000/api/v1/health >/dev/null && break
    sleep 1
  done
  uv run python scripts/gov_mirror.py register
  kill "$api"
  wait "$api" 2>/dev/null || true
fi

echo "done. Backup: $backup"
