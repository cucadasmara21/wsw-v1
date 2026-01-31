# Titan V8 Polling Hotfix - Exact Patch Diff

## Problem
Polling firing every ~5-8ms instead of minimum 2000ms, causing request flood and 500 errors.

## Solution
Strict completion-chained polling with single-flight guard, enforced minimum 2000ms interval, and proper cleanup.

---

## Patch Diff for `frontend/src/components/TitanCanvas.tsx`

### 1. Update Refs (Remove old, add new)

```diff
@@ -442,6 +442,10 @@ export const TitanCanvas = forwardRef<TitanCanvasRef, TitanCanvasProps>(({
-  const pollTimeoutRef = useRef<number | null>(null)
   const inFlightRef = useRef(false)
+  const pollTimerRef = useRef<number | null>(null)
   const abortRef = useRef<AbortController | null>(null)
-  const backoffDelayRef = useRef<number>(0) // Current backoff delay in ms
-  const cancelledRef = useRef(false) // Guard to prevent scheduling after unmount
+  const unmountedRef = useRef(false)
   const symbolsLoadedRef = useRef(false) // Load symbols only once
```

### 2. Replace fetchData with fetchPointsBinary and fetchSymbolsIfNeeded

```diff
@@ -537,6 +537,95 @@ export const TitanCanvas = forwardRef<TitanCanvasRef, TitanCanvasProps>(({
-  async function fetchData(signal?: AbortSignal): Promise<{ success: boolean; shouldBackoff: boolean }> {
-    // Single-flight guard: prevent overlapping requests
-    if (inFlightRef.current) {
-      return { success: false, shouldBackoff: false }
-    }
-    inFlightRef.current = true
-
-    const fetchStart = performance.now()
-    let success = false
-    let shouldBackoff = false
-
-    try {
-      // Fetch points.bin first (sequential, not parallel)
-      const binRes = await fetch(streamUrlBin, { signal })
-      
-      if (signal?.aborted) {
-        return { success: false, shouldBackoff: false }
-      }
-
-      if (!binRes.ok) {
-        // HTTP error (500, etc.) - apply backoff
-        shouldBackoff = true
-        return { success: false, shouldBackoff: true }
-      }
-      
-      const ab = await binRes.arrayBuffer()
-      
-      if (signal?.aborted) {
-        return { success: false, shouldBackoff: false }
-      }
-
-      if (ab.byteLength === 0) {
-        return { success: false, shouldBackoff: false }
-      }
-      
-      if (ab.byteLength % 12 !== 0) {
-        return { success: false, shouldBackoff: false }
-      }
-      
-      const count = Math.floor(ab.byteLength / 12)
-      vertexCountRef.current = count
-      bufferDataRef.current = ab
-      
-      const bounds = computeBounds(ab, count)
-      boundsRef.current = bounds
-      
-      // Only fetch symbols once on startup, not on every poll (reduces load by 50%)
-      if (!symbolsLoadedRef.current) {
-        let symbolsMap = new Map<number, string>()
-        try {
-          const symbolsRes = await fetch('/api/universe/points.symbols?limit=10000', { signal })
-          
-          if (signal?.aborted) {
-            return { success: false, shouldBackoff: false }
-          }
-
-          if (symbolsRes.ok) {
-            try {
-              const symbolsData = await symbolsRes.json()
-              symbolsData.symbols?.forEach((item: any, idx: number) => {
-                symbolsMap.set(idx + 1, item.symbol || `ASSET-${item.id}`)
-              })
-              symbolsLoadedRef.current = true
-              symbolsMapRef.current = symbolsMap
-            } catch {
-              // Ignore symbols parse errors
-            }
-          }
-        } catch {
-          // Ignore symbols fetch errors (non-critical)
-        }
-      }
-      
-      // Use existing symbols map (loaded once or empty)
-      const symbolsMap = symbolsMapRef.current || new Map()
-      const decoded = await decodePoints(ab, symbolsMap, bounds)
-      pointsDataRef.current = decoded
-      
-      // Compute globalShockFactor from sample of points (cheap, O(K) where K=256)
-      const sampleSize = Math.min(256, decoded.length)
-      let shockSum = 0.0
-      for (let i = 0; i < sampleSize; i++) {
-        shockSum += decoded[i].shock
-      }
-      globalShockFactorRef.current = sampleSize > 0 ? shockSum / sampleSize : 0.0
-      
-      const fetchMs = Math.round(performance.now() - fetchStart)
-      
-      setStats(prev => ({
-        ...prev,
-        points: count,
-        bytes: ab.byteLength,
-        stride: 12,
-        fetchMs,
-        xMin: bounds.minX,
-        xMax: bounds.maxX,
-        yMin: bounds.minY,
-        yMax: bounds.maxY,
-        xyDegen: bounds.degenerate,
-        uniqueX512: bounds.uniqueX,
-        uniqueY512: bounds.uniqueY,
-        dataDegenerateFallback: bounds.degenerate
-      }))
-      
-      const gl = glRef.current
-      const vbo = bufferRef.current
-      if (gl && vbo && count > 0) {
-        gl.bindBuffer(gl.ARRAY_BUFFER, vbo)
-        const u8 = new Uint8Array(ab)
-        gl.bufferData(gl.ARRAY_BUFFER, u8, gl.DYNAMIC_DRAW)
-        gl.bindBuffer(gl.ARRAY_BUFFER, null)
-      }
-
-      success = true
-      // Reset backoff on success
-      backoffDelayRef.current = 0
-    } catch (err) {
-      // Ignore abort errors
-      if (err instanceof Error && err.name === 'AbortError') {
-        return { success: false, shouldBackoff: false }
-      }
-      // Network/other errors - apply backoff
-      shouldBackoff = true
-    } finally {
-      inFlightRef.current = false
-    }
-
-    return { success, shouldBackoff }
-  }
+  // Helper to clear poll timer
+  const clearPollTimer = useCallback(() => {
+    if (pollTimerRef.current != null) {
+      window.clearTimeout(pollTimerRef.current)
+      pollTimerRef.current = null
+    }
+  }, [])
+
+  // Fetch points.bin (extracted for reuse)
+  const fetchPointsBinary = useCallback(async (signal?: AbortSignal): Promise<void> => {
+    const fetchStart = performance.now()
+    const binRes = await fetch(streamUrlBin, { signal })
+    
+    if (signal?.aborted) {
+      throw new DOMException('Aborted', 'AbortError')
+    }
+
+    if (!binRes.ok) {
+      throw new Error(`points.bin HTTP ${binRes.status}`)
+    }
+    
+    const ab = await binRes.arrayBuffer()
+    
+    if (signal?.aborted) {
+      throw new DOMException('Aborted', 'AbortError')
+    }
+
+    if (ab.byteLength === 0) {
+      return
+    }
+    
+    if (ab.byteLength % 12 !== 0) {
+      return
+    }
+    
+    const count = Math.floor(ab.byteLength / 12)
+    vertexCountRef.current = count
+    bufferDataRef.current = ab
+    
+    const bounds = computeBounds(ab, count)
+    boundsRef.current = bounds
+    
+    // Use existing symbols map (loaded once or empty)
+    const symbolsMap = symbolsMapRef.current || new Map()
+    const decoded = await decodePoints(ab, symbolsMap, bounds)
+    pointsDataRef.current = decoded
+    
+    // Compute globalShockFactor from sample of points (cheap, O(K) where K=256)
+    const sampleSize = Math.min(256, decoded.length)
+    let shockSum = 0.0
+    for (let i = 0; i < sampleSize; i++) {
+      shockSum += decoded[i].shock
+    }
+    globalShockFactorRef.current = sampleSize > 0 ? shockSum / sampleSize : 0.0
+    
+    const fetchMs = Math.round((performance.now() - fetchStart))
+    
+    setStats(prev => ({
+      ...prev,
+      points: count,
+      bytes: ab.byteLength,
+      stride: 12,
+      fetchMs,
+      xMin: bounds.minX,
+      xMax: bounds.maxX,
+      yMin: bounds.minY,
+      yMax: bounds.maxY,
+      xyDegen: bounds.degenerate,
+      uniqueX512: bounds.uniqueX,
+      uniqueY512: bounds.uniqueY,
+      dataDegenerateFallback: bounds.degenerate
+    }))
+    
+    const gl = glRef.current
+    const vbo = bufferRef.current
+    if (gl && vbo && count > 0) {
+      gl.bindBuffer(gl.ARRAY_BUFFER, vbo)
+      const u8 = new Uint8Array(ab)
+      gl.bufferData(gl.ARRAY_BUFFER, u8, gl.DYNAMIC_DRAW)
+      gl.bindBuffer(gl.ARRAY_BUFFER, null)
+    }
+  }, [streamUrlBin])
+
+  // Fetch symbols if needed (only once)
+  const fetchSymbolsIfNeeded = useCallback(async (signal?: AbortSignal): Promise<void> => {
+    if (symbolsLoadedRef.current) {
+      return
+    }
+
+    try {
+      const symbolsRes = await fetch('/api/universe/points.symbols?limit=10000', { signal })
+      
+      if (signal?.aborted) {
+        throw new DOMException('Aborted', 'AbortError')
+      }
+
+      if (symbolsRes.ok) {
+        const symbolsData = await symbolsRes.json()
+        const symbolsMap = new Map<number, string>()
+        symbolsData.symbols?.forEach((item: any, idx: number) => {
+          symbolsMap.set(idx + 1, item.symbol || `ASSET-${item.id}`)
+        })
+        symbolsLoadedRef.current = true
+        symbolsMapRef.current = symbolsMap
+      }
+    } catch (err: any) {
+      if (err?.name === 'AbortError') {
+        throw err
+      }
+      // Ignore symbols fetch errors (non-critical)
+    }
+  }, [])
```

### 3. Replace Polling Logic with pollOnce()

```diff
@@ -966,6 +966,35 @@ export const TitanCanvas = forwardRef<TitanCanvasRef, TitanCanvasProps>(({
     renderLoopRef.current = requestAnimationFrame(render)
 
-    // Enforce minimum polling interval of 2000ms
-    const basePollMs = Math.max(2000, pollMs > 0 ? pollMs : 2000)
-
-    // Create AbortController for this effect instance
-    const abortController = new AbortController()
-    abortRef.current = abortController
-    cancelledRef.current = false
-    symbolsLoadedRef.current = false // Reset symbols on new effect instance
-
-    // Chained setTimeout polling: schedule next tick only after previous fetch completes
-    // CRITICAL: Schedule ONLY ONCE per fetch completion to prevent storm
-    const scheduleNextPoll = () => {
-      // Guard: do not schedule if cancelled or aborted
-      if (cancelledRef.current || abortController.signal.aborted) {
-        return
-      }
-
-      // Calculate delay: base interval + backoff
-      const effectivePollMs = basePollMs + backoffDelayRef.current
-
-      // Clear any existing timeout (safety)
-      if (pollTimeoutRef.current) {
-        clearTimeout(pollTimeoutRef.current)
-        pollTimeoutRef.current = null
-      }
-
-      // Schedule next poll
-      pollTimeoutRef.current = window.setTimeout(async () => {
-        // Guard: check cancelled/aborted before starting
-        if (cancelledRef.current || abortController.signal.aborted) {
-          return
-        }
-
-        // Single-flight guard: prevent overlapping
-        if (inFlightRef.current) {
-          // If already in flight, reschedule with base delay (don't accumulate backoff)
-          scheduleNextPoll()
-          return
-        }
-
-        // Execute fetch
-        const result = await fetchData(abortController.signal)
-        
-        // Schedule next poll ONLY ONCE, here in completion handler
-        if (!cancelledRef.current && !abortController.signal.aborted) {
-          if (result.shouldBackoff) {
-            // Apply exponential backoff (capped at 30s)
-            backoffDelayRef.current = Math.min(30000, Math.max(basePollMs * 2, (backoffDelayRef.current || basePollMs) * 2))
-          } else {
-            // Reset backoff on success
-            backoffDelayRef.current = 0
-          }
-          // Schedule next poll (ONLY HERE - single scheduling point)
-          scheduleNextPoll()
-        }
-      }, effectivePollMs)
-    }
-
-    // Initial fetch - use same completion handler pattern
-    const runInitialFetch = async () => {
-      if (cancelledRef.current || abortController.signal.aborted) {
-        return
-      }
-      const result = await fetchData(abortController.signal)
-      if (!cancelledRef.current && !abortController.signal.aborted) {
-        if (result.shouldBackoff) {
-          backoffDelayRef.current = Math.min(30000, basePollMs * 2)
-        }
-        scheduleNextPoll()
-      }
-    }
-    runInitialFetch()
+    // Polling: completion-chained with single-flight guard
+    const pollOnce = useCallback(async () => {
+      if (unmountedRef.current) return
+      if (inFlightRef.current) return
+
+      const effectivePollMs = Math.max(2000, pollMs > 0 ? pollMs : 2000)
+
+      inFlightRef.current = true
+      clearPollTimer()
+
+      abortRef.current?.abort()
+      const ac = new AbortController()
+      abortRef.current = ac
+
+      try {
+        await fetchPointsBinary({ signal: ac.signal })
+        await fetchSymbolsIfNeeded({ signal: ac.signal })
+      } catch (err: any) {
+        if (err?.name !== 'AbortError') {
+          console.error('pollOnce error', err)
+        }
+      } finally {
+        inFlightRef.current = false
+        if (unmountedRef.current) return
+        pollTimerRef.current = window.setTimeout(pollOnce, effectivePollMs)
+      }
+    }, [pollMs, fetchPointsBinary, fetchSymbolsIfNeeded, clearPollTimer])
+
+    // Start polling
+    unmountedRef.current = false
+    symbolsLoadedRef.current = false // Reset symbols on new effect instance
+    pollOnce()
 
     return () => {
-      // Mark as cancelled to prevent any new scheduling
-      cancelledRef.current = true
-      
-      // Abort any in-flight requests
-      abortController.abort()
+      unmountedRef.current = true
+      clearPollTimer()
+      abortRef.current?.abort()
       abortRef.current = null
       inFlightRef.current = false
       
       if (renderLoopRef.current) {
         cancelAnimationFrame(renderLoopRef.current)
       }
       window.removeEventListener('keydown', handleKeyPress)
       resizeObserver.disconnect()
       if (pickingWorkerRef.current) {
         pickingWorkerRef.current.terminate()
         pickingWorkerRef.current = null
       }
       if (vaoRef.current) gl.deleteVertexArray(vaoRef.current)
       if (bufferRef.current) gl.deleteBuffer(bufferRef.current)
       if (programRef.current) gl.deleteProgram(programRef.current)
       if (debugProgramRef.current) gl.deleteProgram(debugProgramRef.current)
     }
-  }, [streamUrlBin, pollMs, onAssetClick])
+  }, [streamUrlBin, pollMs, onAssetClick, fetchPointsBinary, fetchSymbolsIfNeeded, clearPollTimer])
```

### 4. Update refresh() method

```diff
@@ -520,6 +520,10 @@ export const TitanCanvas = forwardRef<TitanCanvasRef, TitanCanvasProps>(({
   useImperativeHandle(ref, () => ({
     refresh: () => {
-      fetchData(abortRef.current?.signal)
+      // Trigger manual refresh by calling pollOnce logic directly
+      if (!inFlightRef.current && !unmountedRef.current) {
+        const ac = new AbortController()
+        abortRef.current?.abort()
+        abortRef.current = ac
+        fetchPointsBinary({ signal: ac.signal }).catch(() => {})
+      }
     },
```

---

## Validation

### Test in Chrome DevTools

1. **Open DevTools** → Network tab
2. **Filter**: `points.bin`
3. **Wait 10 seconds**
4. **Expected**: Maximum 5 requests (one every 2 seconds)
5. **Check**: No overlapping pending requests (each request should complete before next starts)

### Verification Commands

```powershell
# Check backend is running
curl.exe -s "http://127.0.0.1:8000/api/universe/points.meta?limit=5"

# Expected: {"count":5,"bytes":60,"stride":12}
```

### Expected Behavior

- ✅ **No setInterval**: Only `setTimeout` used, chained in `finally` block
- ✅ **Minimum 2000ms**: `effectivePollMs = Math.max(2000, pollMs > 0 ? pollMs : 2000)`
- ✅ **Single-flight**: `inFlightRef` guard prevents overlapping requests
- ✅ **Completion-chained**: Next poll scheduled ONLY in `finally` after fetch completes
- ✅ **AbortController**: Previous request aborted before starting new one
- ✅ **Clean unmount**: Timer cleared, abort called, flags reset
- ✅ **No recursive loops**: No `setTimeout(..., 0)` or immediate scheduling

---

## Key Changes Summary

1. **Removed**: `pollTimeoutRef`, `backoffDelayRef`, `cancelledRef`, `scheduleNextPoll()`, `runInitialFetch()`, `fetchData()`
2. **Added**: `pollTimerRef`, `unmountedRef`, `clearPollTimer()`, `fetchPointsBinary()`, `fetchSymbolsIfNeeded()`, `pollOnce()`
3. **Structure**: Single `pollOnce()` async function that schedules itself in `finally` block
4. **Guards**: `unmountedRef` and `inFlightRef` prevent scheduling when unmounted or already in flight
5. **Enforcement**: `effectivePollMs = Math.max(2000, pollMs > 0 ? pollMs : 2000)` ensures minimum 2000ms

---

## How to Verify Fix

1. **Start backend**: `uvicorn main:app --host 127.0.0.1 --port 8000 --reload`
2. **Start frontend**: `npm run dev` in `frontend/` directory
3. **Open**: `http://127.0.0.1:5173/universe`
4. **Open DevTools** → Network → Filter: `points.bin`
5. **Observe**: Requests should appear at most once every 2 seconds
6. **Check**: No 500 errors from backend flood
7. **Verify**: No overlapping pending requests

---

## Acceptance Criteria

✅ **No setInterval**: Only `setTimeout` used  
✅ **Minimum 2000ms**: Enforced via `Math.max(2000, pollMs > 0 ? pollMs : 2000)`  
✅ **Single-flight**: `inFlightRef` guard honored  
✅ **Completion-chained**: Next poll scheduled ONLY in `finally`  
✅ **AbortController**: Used for cancellation  
✅ **Clean unmount**: Timer cleared, abort called  
✅ **No recursive loops**: No immediate scheduling  
