# PHASE 0: points.bin Fetch Audit Report

## Canonical Poller
**Location**: `frontend/src/components/TitanCanvas.tsx` (lines 970-1056)
- **Type**: Single `useEffect` with completion-chained `setTimeout`
- **Guards**: epoch token (`pollEpochRef`), single-flight (`inFlightRef`), spacing (`lastStartMsRef`)
- **Status**: ✅ This is the ONLY active polling loop

## Other points.bin References (Non-Polling)

### 1. `frontend/src/lib/pointsWorkerClient.ts`
- **Purpose**: Worker-based fetch client
- **Status**: ⚠️ **NOT CURRENTLY USED** - No imports found in active code
- **Action**: Can be removed or kept for future use

### 2. `frontend/src/workers/pointsWorker.ts`
- **Purpose**: Web Worker implementation for fetching points.bin
- **Status**: ⚠️ **NOT CURRENTLY USED** - Only referenced by unused `pointsWorkerClient.ts`
- **Action**: Can be removed or kept for future use

### 3. `frontend/src/lib/api.ts` (line 72)
- **Purpose**: Helper function `fetchApiArrayBuffer('/universe/points.bin?limit=...')`
- **Status**: ✅ Helper only, not used for polling

### 4. `frontend/src/components/UniverseCanvas.tsx` (line 100)
- **Purpose**: One-time load on mount
- **Status**: ✅ Different component, not polling

### 5. `frontend/src/hooks/usePointData.ts` (line 67)
- **Purpose**: Fetches `/api/universe/points.symbols` (different endpoint)
- **Status**: ✅ Not points.bin

## Conclusion

**CANONICAL POLLER**: `TitanCanvas.tsx` useEffect (lines 970-1056)
- ✅ Single polling loop
- ✅ Completion-chained setTimeout
- ✅ Epoch guard prevents StrictMode duplication
- ✅ Single-flight lock prevents overlaps
- ✅ Spacing enforcement via `lastStartMsRef`

**NO DUPLICATE POLLERS FOUND**

## Recommendations

1. **Remove unused code**: `pointsWorkerClient.ts` and `pointsWorker.ts` are not used
2. **Verify StrictMode**: Current implementation should handle double-mount correctly
3. **Monitor Network**: With `pollMs=2000`, expect ≤6 requests in 10 seconds
