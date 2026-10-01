# DR restore drill

**Run: 1 October 2026, base M2, TimescaleDB in Docker.** Reproduce with `make dr-drill`
(`scripts/dr_drill.sh`). Each run writes its dump, role export, per-table counts and a
report to `var/dr-drill/<timestamp>/`.

## What the drill does

1. `pg_dump -Fc` of the live database, plus `pg_dumpall --roles-only` so a fresh
   cluster at the DR site gets the `sentinel_app` role that row-level security depends on.
2. Restore into a brand-new database next to the live one.
3. Compare every table's row count and the Alembic migration head.
4. Verify the audit hash chain on the **restored** copy (`scripts/verify_audit_log.py`).
5. Edit one restored audit row and confirm verification now **fails**, so a pass in
   step 4 is evidence, not a formality.

The live database is only read. The restored copy is dropped at the end.

## Results

| Check | Seeded demo data | + 1,000,000 synthetic detections |
|---|---|---|
| Backup size / time | 75 KB / 0.4 s | 23.4 MB / 1.6 s |
| Restore into a fresh database | 0.5 s | **5.7 s** |
| Row counts, all 15 tables | identical | identical |
| Migration head `7b2c4e1f9a10` | identical | identical |
| Audit chain after restore | intact | intact |
| Tampered row detected after restore | yes | yes |

## What the first run found

The first attempt **failed**: `pg_restore` stopped on
`table "detections" is not a hypertable`. Detections are a TimescaleDB hypertable,
and a plain restore cannot recreate its chunks' foreign keys. The documented fix is to
bracket the restore with `timescaledb_pre_restore()` and `timescaledb_post_restore()`.
The drill now does this. Without the drill, the team would have learned it during an
outage.

## What this does and does not prove

- **Proves:** the backup is complete and restorable, row-level security roles travel
  with it, and the hash-chained audit log survives a restore with its tamper
  evidence intact.
- **Does not prove the 1-hour RTO.** At the measured 5.7 s per million detections,
  a year of statewide detections (about 17.8 billion rows at 48.7 M/day,
  `docs/04-SCALE-PLAN.md` §4.2) would take about a day to restore logically on one
  core. That is why the RTO rests on Patroni failover to a synchronous replica and
  physical, parallel point-in-time restore (§5), not on `pg_dump`. Logical dumps are
  the second line: a portable, verifiable copy for the registry, watchlist, alerts
  and audit log, which are small and restore in seconds.
- Evidence snapshots and clips live in object storage and are replicated there; their
  integrity is checked by the SHA-256 hashes in each movement-report manifest.
