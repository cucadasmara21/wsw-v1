# DB Contract (TITAN V8 Route A)

## assets TABLE vs assets_v8 VIEW

- **public.assets**: ORM TABLE. Insertable. Used by legacy endpoints, seed_ontology, tests.
- **public.assets_v8**: VIEW over universe_assets. Read-only. Route A compatibility layer.

Both exist; neither replaces the other. API reads from `public.assets` (TABLE).

## Stable Identity

- **ORM assets**: integer `id` (serial), stable once inserted.
- **universe_assets**: `asset_id` UUID, stable. Synthetic seed uses `uuid5(namespace, symbol)` for determinism.
- **assets_v8 view**: `asset_uid` = asset_id::text (stable); `id` = deterministic from hashtext(symbol).

## Provenance (Optional)

When `ENABLE_PROVENANCE=true`:

- `universe_assets` gets: ingestion_run_id, source, observed_at, row_digest.
- Use `services.provenance.compute_row_digest(columns)` for tamper detection.
- Default: false (CI-safe).

## Type-Safe DDL

Always use `drop_relation_type_safe(conn, schema, name)` — never raw `DROP VIEW IF EXISTS` on objects that may be TABLEs. Detects relkind via pg_class.

## Running Postgres Locally

```bash
docker run -d --name wsw-pg -e POSTGRES_USER=test_user -e POSTGRES_PASSWORD=test_password -e POSTGRES_DB=test_db -p 5432:5432 postgres:15
export DATABASE_URL=postgresql://test_user:test_password@localhost:5432/test_db
python init_db.py
```
