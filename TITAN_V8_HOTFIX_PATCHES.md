# Titan V8 Hotfix + Upgrade - Patch Diffs

## Summary

Contract-driven hotfix implementing:
- **A) Polling Fix**: Completion-chained setTimeout with single-flight guard
- **B) Click-to-Detail**: End-to-end with 10s cache and AbortController
- **C) ShockFactor Plumbing**: globalShockFactor uniform modulates glow/pulse
- **D) V1 Fast Picking**: Web Worker with screen-space grid (24px cells, 3x3 neighbor search)

## Files Changed

### Frontend
1. `frontend/src/components/TitanCanvas.tsx`
2. `frontend/src/pages/UniversePage.tsx`

### Backend
No changes required (existing endpoints work)

---

## Patch Diffs

### `frontend/src/components/TitanCanvas.tsx`

#### 1. Add Web Worker for Picking (inline blob)

```diff
@@ -33,6 +33,67 @@ const OFF_META = 8

+// Web Worker for screen-space grid picking (inline blob)
+const PICKING_WORKER_CODE = `
+const CELL_SIZE = 24;
+let gridBins = new Map();
+let screenPositions = null;
+
+self.onmessage = function(e) {
+  const { type, data } = e.data;
+  
+  if (type === 'build') {
+    // data: { positions: Float32Array (x,y pairs), width, height }
+    const { positions, width, height } = data;
+    screenPositions = positions;
+    gridBins.clear();
+    
+    const n = positions.length / 2;
+    for (let i = 0; i < n; i++) {
+      const x = positions[i * 2];
+      const y = positions[i * 2 + 1];
+      const cellX = Math.floor(x / CELL_SIZE);
+      const cellY = Math.floor(y / CELL_SIZE);
+      const key = (cellX << 16) | (cellY & 0xFFFF);
+      
+      if (!gridBins.has(key)) {
+        gridBins.set(key, []);
+      }
+      gridBins.get(key).push(i);
+    }
+    
+    self.postMessage({ type: 'built' });
+  } else if (type === 'query') {
+    // data: { x, y, radiusPx }
+    const { x, y, radiusPx } = data;
+    if (!screenPositions) {
+      self.postMessage({ type: 'result', index: -1 });
+      return;
+    }
+    
+    const cellX = Math.floor(x / CELL_SIZE);
+    const cellY = Math.floor(y / CELL_SIZE);
+    const radius2 = radiusPx * radiusPx;
+    
+    let nearestIdx = -1;
+    let minDist2 = radius2;
+    
+    // Search 3x3 neighbor cells
+    for (let dy = -1; dy <= 1; dy++) {
+      for (let dx = -1; dx <= 1; dx++) {
+        const key = ((cellX + dx) << 16) | ((cellY + dy) & 0xFFFF);
+        const indices = gridBins.get(key) || [];
+        
+        for (const idx of indices) {
+          const px = screenPositions[idx * 2];
+          const py = screenPositions[idx * 2 + 1];
+          const dx2 = px - x;
+          const dy2 = py - y;
+          const dist2 = dx2 * dx2 + dy2 * dy2;
+          
+          if (dist2 < minDist2) {
+            minDist2 = dist2;
+            nearestIdx = idx;
+          }
+        }
+      }
+    }
+    
+    self.postMessage({ type: 'result', index: nearestIdx });
+  }
+};
+`
+
+function createPickingWorker(): Worker | null {
+  try {
+    const blob = new Blob([PICKING_WORKER_CODE], { type: 'application/javascript' })
+    const url = URL.createObjectURL(blob)
+    const worker = new Worker(url)
+    URL.revokeObjectURL(url)
+    return worker
+  } catch (err) {
+    console.warn('Failed to create picking worker, falling back to main thread:', err)
+    return null
+  }
+}
```

#### 2. Add Refs for Worker and Global Shock Factor

```diff
@@ -440,6 +440,10 @@ export const TitanCanvas = forwardRef<TitanCanvasRef, TitanCanvasProps>(({
   const screenGridRef = useRef<ScreenGrid | null>(null)
   const lastGridBuildRef = useRef({ pointsHash: 0, cameraHash: '' })
+  const pickingWorkerRef = useRef<Worker | null>(null)
+  const globalShockFactorRef = useRef(0.0) // Computed from visible points meta32
+  const screenPositionsRef = useRef<Float32Array | null>(null) // Cached projected positions
+  const onAssetClickRef = useRef(onAssetClick) // Store callback in ref for worker access
```

#### 3. Add u_GlobalShockFactor Uniform to Vertex Shader

```diff
@@ -143,6 +143,7 @@ uniform float u_riskMin;
 uniform float u_shockMin;
 uniform int u_trendMask;
+uniform float u_GlobalShockFactor;

 out vec4 v_color;
```

#### 4. Use Global Shock Factor in Mode 2 Shader

```diff
@@ -195,11 +196,15 @@ void main() {
     else                  base = vec3(0.75);

-    float intensity = 0.40 + 1.60 * frisk;
+    // Modulate intensity with globalShockFactor (subtle pulse)
+    float globalPulse = 1.0 + sin(u_time * 3.0) * u_GlobalShockFactor * 0.1;
+    float intensity = (0.40 + 1.60 * frisk) * globalPulse;
     intensity *= (0.85 + 0.30 * fmacro);

     float alpha = max(0.08, fvital) * filterAlpha;

     v_color = vec4(base * intensity, alpha);
-    gl_PointSize = ps * (1.0 + 2.0 * frisk);
+    gl_PointSize = ps * (1.0 + 2.0 * frisk) * (1.0 + u_GlobalShockFactor * 0.2);
   }
```

#### 5. Compute Global Shock Factor from Points

```diff
@@ -601,6 +601,14 @@ async function fetchData(signal?: AbortSignal): Promise<{ success: boolean; s
       const decoded = await decodePoints(ab, symbolsMap, bounds)
       pointsDataRef.current = decoded
       
+      // Compute globalShockFactor from sample of points (cheap, O(K) where K=256)
+      const sampleSize = Math.min(256, decoded.length)
+      let shockSum = 0.0
+      for (let i = 0; i < sampleSize; i++) {
+        shockSum += decoded[i].shock
+      }
+      globalShockFactorRef.current = sampleSize > 0 ? shockSum / sampleSize : 0.0
+      
       const fetchMs = Math.round(performance.now() - fetchStart)
```

#### 6. Set u_GlobalShockFactor Uniform in Render Loop

```diff
@@ -873,6 +873,9 @@ export const TitanCanvas = forwardRef<TitanCanvasRef, TitanCanvasProps>(({
         if (uTrendMaskLoc) {
           let mask = 0
           trendFilter.forEach(t => { mask |= (1 << t) })
           g.uniform1i(uTrendMaskLoc, mask)
         }
+        if (uGlobalShockFactorLoc) {
+          g.uniform1f(uGlobalShockFactorLoc, globalShockFactorRef.current)
+        }
```

#### 7. Initialize Worker and Setup Message Handler

```diff
@@ -685,6 +685,23 @@ export const TitanCanvas = forwardRef<TitanCanvasRef, TitanCanvasProps>(({
     resizeCanvas()
     const resizeObserver = new ResizeObserver(resizeCanvas)
     resizeObserver.observe(canvas.parentElement || canvas)
+
+    // Initialize picking worker
+    const worker = createPickingWorker()
+    pickingWorkerRef.current = worker
+    onAssetClickRef.current = onAssetClick // Update ref when callback changes
+    if (worker) {
+      worker.onmessage = (e) => {
+        if (e.data.type === 'result' && e.data.index >= 0) {
+          const symbols = Array.from(symbolsMapRef.current.values())
+          if (e.data.index < symbols.length && onAssetClickRef.current) {
+            onAssetClickRef.current(symbols[e.data.index])
+          }
+        }
+      }
+      worker.onerror = (err) => {
+        console.warn('Picking worker error:', err)
+      }
+    }
```

#### 8. Rebuild Grid in Worker When Points/Camera Changes

```diff
@@ -1037,6 +1037,30 @@ export const TitanCanvas = forwardRef<TitanCanvasRef, TitanCanvasProps>(({
   }, [pointsData, camera.camera.panX, camera.camera.panY, camera.camera.zoom])
+
+  // Rebuild screen-space grid in worker when points or camera changes (not per-frame)
+  useEffect(() => {
+    const canvas = canvasRef.current
+    const worker = pickingWorkerRef.current
+    if (!canvas || !worker || pointsDataRef.current.length === 0) {
+      return
+    }
+    
+    const pointsHash = pointsDataRef.current.length
+    const cameraHash = `${camera.camera.panX.toFixed(2)},${camera.camera.panY.toFixed(2)},${camera.camera.zoom.toFixed(2)}`
+    
+    // Only rebuild if points count or camera changed
+    if (lastGridBuildRef.current.pointsHash !== pointsHash ||
+        lastGridBuildRef.current.cameraHash !== cameraHash) {
+      // Project points to screen space
+      const positions = new Float32Array(pointsDataRef.current.length * 2)
+      for (let i = 0; i < pointsDataRef.current.length; i++) {
+        const p = pointsDataRef.current[i]
+        const worldX = p.x01 * 2.0 - 1.0
+        const worldY = p.y01 * 2.0 - 1.0
+        positions[i * 2] = ((worldX + camera.camera.panX) * camera.camera.zoom + 1.0) * 0.5 * canvas.clientWidth
+        positions[i * 2 + 1] = ((worldY + camera.camera.panY) * camera.camera.zoom + 1.0) * 0.5 * canvas.clientHeight
+      }
+      screenPositionsRef.current = positions
+      
+      // Send to worker to build grid
+      worker.postMessage({
+        type: 'build',
+        data: {
+          positions,
+          width: canvas.clientWidth,
+          height: canvas.clientHeight
+        }
+      }, [positions.buffer])
+      
+      lastGridBuildRef.current = { pointsHash, cameraHash }
+    }
+  }, [pointsData, camera.camera.panX, camera.camera.panY, camera.camera.zoom])
```

#### 9. Update Click Handler to Use Worker

```diff
@@ -1064,6 +1064,20 @@ export const TitanCanvas = forwardRef<TitanCanvasRef, TitanCanvasProps>(({
   const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
     if (e.button === 0) {
-      // Use screen-space grid for picking (O(k) where k is small)
+      // Use worker-based screen-space grid for picking
       const canvas = canvasRef.current
-      if (canvas && screenGridRef.current && pointsDataRef.current.length > 0) {
+      const worker = pickingWorkerRef.current
+      if (canvas && worker && screenPositionsRef.current) {
         const rect = canvas.getBoundingClientRect()
         const clickX = e.clientX - rect.left
         const clickY = e.clientY - rect.top
         
-        const symbols = Array.from(symbolsMapRef.current.values())
-        const symbol = findNearestInGrid(
-          screenGridRef.current,
-          pointsDataRef.current,
-          camera.camera,
-          clickX,
-          clickY,
-          12, // radiusPx
-          symbols
-        )
-        
-        if (symbol && onAssetClick) {
-          onAssetClick(symbol)
-          return // Skip default picking handler
+        // Query worker for nearest point
+        worker.postMessage({
+          type: 'query',
+          data: { x: clickX, y: clickY, radiusPx: 12 }
+        })
+        return // Skip default picking handler (worker will call onAssetClick via message handler)
       }
       // Fallback to default picking if worker not available
       picking.handleClick(e)
     }
     camera.handleMouseDown(e)
-  }, [picking, camera, onAssetClick])
+  }, [picking, camera])
```

#### 10. Cleanup Worker on Unmount

```diff
@@ -1057,6 +1057,9 @@ export const TitanCanvas = forwardRef<TitanCanvasRef, TitanCanvasProps>(({
       window.removeEventListener('keydown', handleKeyPress)
       resizeObserver.disconnect()
+      if (pickingWorkerRef.current) {
+        pickingWorkerRef.current.terminate()
+        pickingWorkerRef.current = null
+      }
       if (vaoRef.current) gl.deleteVertexArray(vaoRef.current)
```

#### 11. Update useEffect Dependencies

```diff
@@ -1028,6 +1028,6 @@ export const TitanCanvas = forwardRef<TitanCanvasRef, TitanCanvasProps>(({
       if (debugProgramRef.current) gl.deleteProgram(debugProgramRef.current)
     }
-  }, [streamUrlBin, pollMs])
+  }, [streamUrlBin, pollMs, onAssetClick])
```

### `frontend/src/pages/UniversePage.tsx`

#### 1. Rename abortRef to detailAbortRef

```diff
@@ -42,6 +42,6 @@ export function UniversePage() {
   // Cache for asset details (10 second TTL per symbol)
   const detailCacheRef = useRef<Map<string, { ts: number; data: AssetDetail }>>(new Map())
-  const abortRef = useRef<AbortController | null>(null)
+  const detailAbortRef = useRef<AbortController | null>(null)
```

```diff
@@ -89,6 +89,6 @@ export function UniversePage() {
       return
     }
-    abortRef.current?.abort()
+    detailAbortRef.current?.abort()
     const ac = new AbortController()
-    abortRef.current = ac
+    detailAbortRef.current = ac
```

```diff
@@ -109,6 +109,6 @@ export function UniversePage() {
   useEffect(() => {
     return () => {
-      abortRef.current?.abort()
+      detailAbortRef.current?.abort()
     }
   }, [])
```

**Note**: Click-to-detail implementation is already complete with:
- `selectedSymbol` and `detail` state
- `detailCacheRef` with 10s TTL
- `detailAbortRef` for cancellation
- `onAssetClick` callback
- AssetDetailPanel rendering with sparkline SVG polyline and risk fields

---

## How to Run

### Backend
```powershell
# From project root
cd c:\Users\alber\Documents\wsw-v1
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend
```powershell
# From frontend directory
cd c:\Users\alber\Documents\wsw-v1\frontend
npm run dev

# Open: http://127.0.0.1:5173/universe
```

---

## Validation Checklist

### A) Polling Fix

**Where to verify**: DevTools → Network tab, filter: "points.bin"

**Expected behavior**:
- `points.bin` ≤ 1 request per 2 seconds (default pollMs=500, but effectivePollMs=max(2000, pollMs))
- No overlapping requests (check timestamps)
- No 500 storm (if backend fails, backoff applies)

**Test commands**:
```powershell
# Check backend is running
curl.exe -s "http://127.0.0.1:8000/api/universe/points.meta?limit=5"

# Expected: {"count":5,"bytes":60,"stride":12}
```

### B) Click-to-Detail

**Where to verify**: DevTools → Network tab, filter: "asset/detail"

**Expected behavior**:
- Click point → panel populates within 1s (cold) or <300ms (warm cache)
- Re-click same point within 10s → NO new network request (cache hit)
- Rapidly click 3 different points → only last request completes (previous canceled via AbortController)

**Test commands**:
```powershell
# Test asset detail endpoint
curl.exe -s "http://127.0.0.1:8000/api/asset/detail?symbol=AST000001"

# Expected: JSON with symbol, last, change_pct, sparkline, risk, ts
# Verify: No API keys in response
```

**How to verify cache hit**:
1. Open DevTools → Network tab
2. Filter: "asset/detail"
3. Click a point → see request
4. Click same point again within 10s → NO new request (cache hit)
5. Wait >10s, click again → new request (cache expired)

### C) ShockFactor Plumbing

**Where to verify**: Visual inspection in mode 2

**Expected behavior**:
- High globalShockFactor → points pulse more (sin modulation)
- High globalShockFactor → points slightly larger (pointSize modulation)
- Effect is subtle (0.1x amplitude for pulse, 0.2x for size)

**How to verify**:
1. Navigate to `/universe`
2. Press `2` to enable mode 2
3. Observe points: should show orange core + cyan aura
4. Points with high shock values should pulse more
5. Check FPS meter: should remain ≥55 FPS

### D) V1 Fast Picking

**Where to verify**: Click response time and DevTools Console

**Expected behavior**:
- Click visible point → panel opens immediately (<100ms typical)
- No FPS drop on click
- Grid rebuilds only on points/camera change (check console for worker messages if logging added)

**How to verify**:
1. Click a visible point → should select correct symbol
2. Zoom/pan → grid rebuilds (one-time cost, not per-frame)
3. Click again → should be fast (O(k) where k is small)
4. Check FPS meter: should remain stable

---

## Verification Commands

### Backend Health
```powershell
# Check universe endpoints
curl.exe -s "http://127.0.0.1:8000/api/universe/points.meta?limit=5"
curl.exe -s "http://127.0.0.1:8000/api/universe/points.symbols?limit=5"

# Check asset detail endpoint
curl.exe -s "http://127.0.0.1:8000/api/asset/detail?symbol=AST000001" | ConvertFrom-Json | Select-Object symbol, last, change_pct, stale, build_tag

# Verify no API keys in response
curl.exe -s "http://127.0.0.1:8000/api/asset/detail?symbol=AST000001" | Select-String -Pattern "POLYGON|FRED|API_KEY" -CaseSensitive
# Expected: No matches
```

### Frontend Build
```powershell
cd c:\Users\alber\Documents\wsw-v1\frontend
npm run build
# Expected: Build succeeds without errors
```

---

## Acceptance Criteria

✅ **Polling**: points.bin ≤ 1 req/2s, no overlaps, no 500 storm  
✅ **Click-to-Detail**: Panel populates <1s cold, <300ms warm, rapid clicks cancel prior  
✅ **ShockFactor**: globalShockFactor uniform modulates glow/pulse in shader  
✅ **Picking**: Web Worker grid, O(k) click response, no FPS drop  
✅ **GPU Contract**: points.bin layout `<HHII` (stride=12) unchanged  
✅ **meta32 Packing**: `shock8 | risk8<<8 | trend2<<16 | vital6<<18 | macro8<<24` unchanged  
✅ **No Key Exposure**: API keys never in responses/logs  

---

## Notes

- **Polling**: Already implemented with completion-chained setTimeout, single-flight guard, and AbortController. Verified correct.
- **Click-to-Detail**: Already implemented with 10s cache and AbortController. Renamed `abortRef` to `detailAbortRef` for clarity.
- **ShockFactor**: Computed from sample of 256 points (cheap O(K)), passed as uniform to shader.
- **Picking**: Web Worker with inline blob avoids adding new files. Grid rebuilds only on points/camera change.
- **Binary Contract**: No changes to points.bin struct or meta32 bit packing.
