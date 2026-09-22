-- Sentinel Platform — database extensions.
--
-- PostGIS: camera geometry and field-of-view polygons (Model 1 gap analysis
-- needs real coverage shapes, not dots on a map).
-- TimescaleDB: hypertables for detections and camera health — 48.7 M detection
-- rows/day at statewide scale, with continuous aggregates behind the dashboards.
-- pg_trgm: fuzzy/partial plate search — rung 4 of the watchlist matching ladder.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
