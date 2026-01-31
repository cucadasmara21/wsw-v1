# Patchset v2 PR Summary

## What is complete vs scaffolded

| Patch | Status | Notes |
|-------|--------|------|
| **P-01** | Complete | `dist = max(1e-9, dist)` in compute_genetic_field + quantumShaders |
| **P-02** | Complete | kappa clamp 1e-3; energy clamp [0,8]; causal_mux denominator guard |
| **P-03** | Complete | WORK_CAP_PER_TICK=50k; realtime_bridge, ingest_service, ingest_batch |
| **P-04** | **Real** | VoidPool try_push/try_pop; Death->release, Birth->acquire in sovereign. |

## Config

- `ENABLE_VOIDPOOL` (default: True): Sovereign uses VoidPool; Death/Birth wired.

## Run tests

```powershell
cd c:\Users\alber\Documents\wsw-v1
python -m pytest tests/test_patchset_v2.py -v --tb=short
cd frontend && npm run test:run -- src/test/vertex28Validation.test.ts
```

## Vertex28

Stride 28 bytes. FAIL_FAST on invalid byteLength.
