-- Quantum materialization objects (Postgres)
-- Provides:
--  - VIEW assets (compat layer used by legacy queries)
--  - MATERIALIZED VIEW universe_snapshot_v8 (fast ordered snapshot for /v8/snapshot)
-- Self-healing: adds missing columns before creating views/MVs

BEGIN;

-- Optional (safe)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Self-heal universe_assets schema (idempotent)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'universe_assets') THEN
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS spin real;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS fidelity_score real;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS vertex_buffer bytea;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS x real;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS y real;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS z real;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS meta32 integer;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS titan_taxonomy32 integer;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS sector text;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS symbol text;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS morton_code bigint;
    END IF;
END $$;

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
  COALESCE(ua.spin, 0.0) AS spin,
  ua.vertex_buffer
FROM public.universe_assets ua
ORDER BY ua.morton_code ASC;

CREATE INDEX IF NOT EXISTS idx_universe_snapshot_v8_morton ON public.universe_snapshot_v8(morton_code);

COMMIT;
