#!/usr/bin/env bash
# Backup -> restore -> verify drill for the central database
# (docs/04-SCALE-PLAN.md: "automated backups with restore verification,
# because an unverified backup is a rumour").
#
# 1. pg_dump the live database (custom format) and the cluster roles.
# 2. Restore into a brand-new database alongside it.
# 3. Compare every table's row count and the migration head.
# 4. Verify the audit hash chain on the restored copy.
# 5. Tamper with one restored audit row and confirm verification FAILS,
#    so a pass in step 4 means something.
# 6. Drop the restored copy. Artefacts stay in var/dr-drill/<timestamp>/.
#
# Usage: make dr-drill    (needs `make up`; reads, never writes, the live DB)
set -euo pipefail

CONTAINER=${SENTINEL_PG_CONTAINER:-sentinel-postgres}
PGUSER=${SENTINEL_DB_USER:-sentinel}
SOURCE=${SENTINEL_DB_NAME:-sentinel}
TARGET="${SOURCE}_dr_drill"
OUT="var/dr-drill/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"

sql() { docker exec -i "$CONTAINER" psql -U "$PGUSER" -v ON_ERROR_STOP=1 -qAt "$@"; }
now_ms() { python3 -c 'import time; print(int(time.time() * 1000))'; }
row_counts() {
  sql -d "$1" -c "
    select table_name || ' ' || (xpath('/row/c/text()', query_to_xml(
      format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text
    from information_schema.tables
    where table_schema = 'public' and table_type = 'BASE TABLE'
    order by table_name"
}
cleanup() { sql -d postgres -c "drop database if exists \"$TARGET\" with (force)" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "== backup: $SOURCE"
t0=$(now_ms)
docker exec "$CONTAINER" pg_dump -U "$PGUSER" -Fc "$SOURCE" > "$OUT/$SOURCE.dump"
docker exec "$CONTAINER" pg_dumpall -U "$PGUSER" --roles-only --no-role-passwords > "$OUT/roles.sql"
t1=$(now_ms)
dump_sha=$(shasum -a 256 "$OUT/$SOURCE.dump" | cut -d' ' -f1)
dump_bytes=$(wc -c < "$OUT/$SOURCE.dump" | tr -d ' ')
echo "   $dump_bytes bytes, sha256 $dump_sha, $((t1 - t0)) ms"

echo "== restore into fresh database: $TARGET"
cleanup
sql -d postgres -c "create database \"$TARGET\"" >/dev/null
t2=$(now_ms)
# detections is a TimescaleDB hypertable: a plain pg_restore fails on its
# chunks' foreign keys. Timescale's documented restore brackets it with
# pre/post_restore. The first run of this drill is how we found out.
sql -d "$TARGET" -c "create extension if not exists timescaledb" -c "select timescaledb_pre_restore()" >/dev/null
docker exec -i "$CONTAINER" pg_restore -U "$PGUSER" -d "$TARGET" --exit-on-error < "$OUT/$SOURCE.dump"
sql -d "$TARGET" -c "select timescaledb_post_restore()" >/dev/null
t3=$(now_ms)
echo "   restored in $((t3 - t2)) ms"

echo "== compare row counts and migration head"
row_counts "$SOURCE" > "$OUT/counts-source.txt"
row_counts "$TARGET" > "$OUT/counts-restored.txt"
if diff -u "$OUT/counts-source.txt" "$OUT/counts-restored.txt"; then
  counts_ok=yes
  echo "   $(wc -l < "$OUT/counts-source.txt" | tr -d ' ') tables, every count identical"
else
  counts_ok=no
fi
head_source=$(sql -d "$SOURCE" -c "select version_num from alembic_version")
head_restored=$(sql -d "$TARGET" -c "select version_num from alembic_version")
[ "$head_source" = "$head_restored" ] && head_ok=yes || head_ok=no
echo "   alembic head $head_source / $head_restored"

echo "== verify audit chain on the restored copy"
chain_out=$(SENTINEL_DB_NAME="$TARGET" uv run --package core_api python scripts/verify_audit_log.py 2>&1) \
  && chain_ok=yes || chain_ok=no
echo "$chain_out" | sed 's/^/   /'

echo "== tamper one restored audit row: verification must now fail"
tampered=$(sql -d "$TARGET" -c "
  update audit_log set action = action || '-tampered'
  where seq = (select min(seq) from audit_log) returning seq")
if [ -z "$tampered" ]; then
  tamper_ok=skipped
  echo "   audit log empty, nothing to tamper with"
elif SENTINEL_DB_NAME="$TARGET" uv run --package core_api python scripts/verify_audit_log.py >/dev/null 2>&1; then
  tamper_ok=no
  echo "   FAILED: a tampered row still verified"
else
  tamper_ok=yes
  echo "   tampered row seq=$tampered detected"
fi

cat > "$OUT/report.md" <<EOF
# DR restore drill $(basename "$OUT")

| Check | Result |
|---|---|
| Backup (pg_dump -Fc + roles) | $dump_bytes bytes in $((t1 - t0)) ms, sha256 \`$dump_sha\` |
| Restore into a fresh database | $((t3 - t2)) ms |
| Row counts, every table | $counts_ok |
| Migration head ($head_source) | $head_ok |
| Audit chain intact after restore | $chain_ok |
| Tampering detected after restore | $tamper_ok |
EOF
echo
cat "$OUT/report.md"

[ "$counts_ok$head_ok$chain_ok" = "yesyesyes" ] && [ "$tamper_ok" != "no" ]
