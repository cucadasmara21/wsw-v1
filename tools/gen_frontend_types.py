"""Generate minimal TypeScript types for frontend from openapi.json.
This is a small fallback generator that extracts the response schemas for /health and /version
and writes a TypeScript file to frontend/src/api/generated.ts
Usage: python tools/gen_frontend_types.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "openapi.json"
OUT = ROOT / "frontend" / "src" / "api" / "generated.ts"

def main():
    if not OPENAPI.exists():
        raise SystemExit("openapi.json not found. Run tools/export_openapi.py first.")
    data = json.loads(OPENAPI.read_text())

    # Extract version response
    version_schema = None
    paths = data.get("paths", {})
    if "/version" in paths:
        responses = paths["/version"].get("get", {}).get("responses", {})
        # Take 200 response schema if present
        r200 = responses.get("200", {}).get("content", {}).get("application/json", {}).get("schema")
        version_schema = r200

    # For /health there may not be a named schema; try to infer shape from example
    health_schema = None
    if "/health" in paths:
        responses = paths["/health"].get("get", {}).get("responses", {})
        r200 = responses.get("200", {}).get("content", {}).get("application/json", {}).get("schema")
        health_schema = r200

    lines = ["// Auto-generated types (fallback generator)", "// Run `python tools/export_openapi.py > openapi.json` and `npm run gen:api` when available", ""]

    # Simple mapper for basic object schemas
    def schema_to_ts(name, schema):
        if not schema:
            return f"export type {name} = any\n"
        # If schema has properties
        props = schema.get("properties")
        if props:
            s = [f"export type {name} = {{" + "\n"]
            for k, v in props.items():
                t = "any"
                typ = v.get("type")
                if typ == "string":
                    t = "string"
                elif typ == "integer" or typ == "number":
                    t = "number"
                elif typ == "boolean":
                    t = "boolean"
                elif typ == "object":
                    t = "Record<string, any>"
                elif typ == "array":
                    t = "any[]"
                else:
                    t = "any"
                s.append(f"  {k}: {t}")
            s.append("}\n")
            return "\n".join(s)
        # fallback
        return f"export type {name} = any\n"

    lines.append(schema_to_ts("Version", version_schema))
    lines.append("\nexport type VersionT = Version\n")
    lines.append(schema_to_ts("Health", health_schema))
    lines.append("\nexport type HealthT = Health\n")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines))
    print(f"Wrote {OUT}")

if __name__ == '__main__':
    main()
