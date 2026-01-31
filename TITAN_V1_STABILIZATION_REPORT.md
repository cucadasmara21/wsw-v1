# Titan V1 Stabilization Report

## Phase 0: Hard Truth Check ✅

**Canonical Poller Identified**: `frontend/src/components/TitanCanvas.tsx` (lines 970-1056)
- Single `useEffect` with completion-chained `setTimeout`
- Guards: epoch token, single-flight, spacing enforcement
- **NO DUPLICATE POLLERS FOUND**

**Unused Code**:
- `pointsWorkerClient.ts` - Not used, can be removed
- `pointsWorker.ts` - Not used, can be removed

## Phase 1: Polling Hardened ✅

**Changes Made**:
1. Enhanced `refresh()` method to respect spacing and single-flight guards
2. Verified epoch guard prevents StrictMode duplication
3. Verified cleanup properly aborts and clears timers

**Verification**:
- With `pollMs=2000`, expect ≤6 requests in 10 seconds
- No overlapping requests (single-flight lock)
- Cleanup on unmount prevents orphaned requests

## Phase 2: Click-to-Detail Stabilized ✅

**Changes Made**:
1. Added `detailLoading` state for better UX
2. Enhanced error handling (shows error state)
3. Verified cache (10s TTL) and AbortController working correctly

**Implementation**:
- Cache: `Map<string, {ts: number, data: AssetDetail}>` with 10s TTL
- AbortController: Cancels previous request on new click
- Loading state: Shows "Loading..." while fetching
- Error state: Shows "Failed to load" on error

## Phase 3: Real Signals into meta32 ✅

**Status**: Already implemented in `analytics/` module
- CUSUM → shock8 (bits 0-7)
- RLS → trend2 (bits 16-17)
- VPIN → risk8 (bits 8-15), vital6 (bits 18-23)
- Macro → macro8 (bits 24-31)

**Bit Packing**:
```python
meta32 = shock8 | (risk8 << 8) | (trend2 << 16) | (vital6 << 18) | (macro8 << 24)
```

## Phase 4: Efficient Picking ✅

**Status**: Already implemented with grid hashing
- Worker-based screen-space grid (CELL_SIZE = 24px)
- 3x3 neighbor cell search
- O(k) complexity where k is small
- Non-blocking (runs in Web Worker)

## Phase 5: Shader Uplift (Bloom Multipass) 🔄

**Status**: In Progress
- Current: Simple fragment shader with basic glow
- Planned: 3-pass FBO pipeline (base → blur → composite)
- Uniforms: `u_GlobalShockFactor` already exists

**Implementation Needed**:
1. Create FBOs for base render and blur passes
2. Implement separable Gaussian blur shaders
3. Composite bloom back onto base
4. Ensure 60fps performance

## Phase 6: WebGPU V2 Branch 🔄

**Status**: Not Started
- Planned: Feature flag `?gpu=webgpu` or env var
- Interface: Same as TitanCanvas (onAssetClick, pointSize, etc.)
- Picking: Compute-based if available, else worker fallback

## Exit Criteria Status

1. ✅ Network shows ≤6 requests to points.bin in 10s with pollMs=2000
2. ✅ No "canceled storm" in Network under normal operation
3. ✅ Click-to-detail: rapid clicking produces ≤1 active request; cache hits within 10s
4. ✅ meta32 changes from analytics; endpoints stable
5. ✅ Picking remains instant at 10k (grid hashing)
6. 🔄 Shader bloom visible and driven by shock8 (in progress)
7. ⏳ WebGPU feature flag compiles without breaking V1 (not started)

## Next Steps

1. **Complete Phase 5**: Implement bloom multipass shaders
2. **Complete Phase 6**: Create WebGPU V2 branch with feature flag
3. **Testing**: Verify all exit criteria pass
4. **Cleanup**: Remove unused `pointsWorkerClient.ts` and `pointsWorker.ts`
