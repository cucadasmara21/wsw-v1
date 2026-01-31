-- Quantum materialization objects (Postgres)
-- Provides:
--  - VIEW assets (compat layer used by legacy queries)
--  - MATERIALIZED VIEW universe_snapshot_v8 (fast ordered snapshot for /v8/snapshot)

BEGIN;

-- Optional (safe)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Compat view: "assets" (id + geometry + meta/taxonomy + has_price)
CREATE OR REPLACE VIEW public.assets AS
SELECT
  sa.asset_id                   AS id,
  sa.symbol                     AS symbol,
  COALESCE(sa.x, 0.0)           AS x,
  COALESCE(sa.y, 0.0)           AS y,
  COALESCE(sa.z, 0.0)           AS z,
  COALESCE(sa.meta32, 0)        AS meta32,
  COALESCE(sa.titan_taxonomy32, 0) AS titan_taxonomy32,
  COALESCE(sa.sector, '')       AS sector,
  EXISTS (SELECT 1 FROM public.prices p WHERE p.asset_id = sa.asset_id LIMIT 1) AS has_price
FROM public.source_assets sa;

-- Snapshot MV: purely from universe_assets (authoritative Vertex28 store)
-- NOTE: universe_assets must already exist (alembic migration).
DROP MATERIALIZED VIEW IF EXISTS public.universe_snapshot_v8;

CREATE MATERIALIZED VIEW public.universe_snapshot_v8 AS
SELECT
  ua.symbol,
  ua.morton_code,
  ua.taxonomy32,
  ua.meta32,
  ua.x,
  ua.y,
  ua.z,
  ua.fidelity_score,
  ua.spin,
  ua.vertex_buffer
FROM public.universe_assets ua
ORDER BY ua.morton_code ASC;

CREATE INDEX IF NOT EXISTS idx_universe_snapshot_v8_morton ON public.universe_snapshot_v8(morton_code);

COMMIT;
