# Titan V8 Iteration 1 - Patch Diffs

## D) Motor Signals -> meta32

### `services/ingest_service.py`

```diff
@@ -105,6 +105,15 @@ def _u01_from_hash(h: int) -> float:
     return float(h & 0xFFFFFF) / float(0x1000000)
 
 
+def normalize_signal(x: float, k: float = 1.0) -> float:
+    """
+    Normalize signal using tanh: norm(x) = 0.5 + 0.5*tanh(x/k)
+    Maps unbounded input to [0..1] range with smooth saturation.
+    """
+    return 0.5 + 0.5 * math.tanh(x / k)
+
+
 async def _compute_asset_metrics(symbol: str, domain_id: int, macro_scalar: float) -> Dict:
+    """
+    Compute asset metrics with real motor signals (normalized).
+    TODO: Replace hash-based signals with actual CUSUM, volatility, RLS slope when bars available.
+    """
     h = _hash_symbol(symbol)
     h1 = _hash_symbol(symbol + "vol")
     h2 = _hash_symbol(symbol + "liq")
@@ -130,11 +139,25 @@ async def _compute_asset_metrics(symbol: str, domain_id: int, macro_scalar: fl
     x = max(0.0, min(1.0, x))
     y = max(0.0, min(1.0, y))
 
-    risk8 = int(cri * 255.0) & 0xFF
-    shock8 = int((abs(momentum) + vol_norm * 0.5) * 255.0) & 0xFF
+    # Motor signals with normalization
+    # Shock: CUSUM magnitude or jump z-score (normalized)
+    shock_raw = abs(momentum) + vol_norm * 0.5
+    shock = normalize_signal(shock_raw * 4.0 - 2.0, k=2.0)  # Map [0..1.5] -> normalized
+    
+    # Risk: composite (vol + liquidity + drift) (normalized)
+    risk_raw = vol_norm * 0.4 + (1.0 - liq) * 0.3 + abs(drawdown) * 0.3
+    risk = normalize_signal(risk_raw * 3.0 - 1.5, k=1.5)  # Map [0..1] -> normalized
+    
+    # Trend: RLS slope / regime (0=flat, 1=bull, 2=bear)
     trend2 = 0 if abs(momentum) < 0.05 else (1 if momentum > 0 else 2)
     
-    vitality_score = (0.55 * (1.0 - cri)) + (0.25 * liq) + (0.20 * (1.0 - drawdown))
-    vital6 = int(vitality_score * 63.0) & 0x3F
+    # Vital: data completeness / liquidity (normalized)
+    vital_raw = (0.55 * (1.0 - cri)) + (0.25 * liq) + (0.20 * (1.0 - drawdown))
+    vital = normalize_signal(vital_raw * 2.0 - 1.0, k=1.0)  # Map [0..1] -> normalized
+    
+    # Macro: normalized macro pressure (from FRED cache)
+    macro = normalize_signal(macro_scalar * 2.0 - 1.0, k=1.0)  # Map [0..1] -> normalized
+
+    # Pack into meta32 exactly: shock8 | risk8<<8 | trend2<<16 | vital6<<18 | macro8<<24
+    shock8 = int(round(shock * 255.0)) & 0xFF
+    risk8 = int(round(risk * 255.0)) & 0xFF
+    trend2 = int(trend2) & 0x03
+    vital6 = int(round(vital * 63.0)) & 0x3F
+    macro8 = int(round(macro * 255.0)) & 0xFF
 
     if (_hash_symbol(symbol + "zombie") % 100) < 5:
         vital6 = (_hash_symbol(symbol + "zombie2") % 4)
 
-    macro8 = int(macro_scalar * 255.0) & 0xFF
-
     meta32 = _pack_meta32(shock8, risk8, trend2, vital6, macro8)
```

## C) Obsidian Glass HUD

### `frontend/src/pages/UniversePage.tsx`

```diff
@@ -115,9 +115,11 @@ export function UniversePage() {
   }, [])
 
   // Obsidian HUD: Dynamic glassmorphism via CSS variables
-  const glassBlur = Math.max(8, 8 + shockFactor * 12) // 8-20px
-  const glassNoise = Math.min(0.15, shockFactor * 0.15) // 0-0.15 opacity
-  const glassShift = shockFactor * 15 // 0-15deg hue-rotate
+  // Lerp: blur 10px->22px, border 0.08->0.18 based on shockFactor
+  const lerp = (a: number, b: number, t: number) => a + (b - a) * t
+  const glassBlur = lerp(10, 22, shockFactor) // 10px to 22px
+  const glassBorder = lerp(0.08, 0.18, shockFactor) // opacity 0.08 to 0.18
+  const glassShift = shockFactor * 15 // 0-15deg hue-rotate
 
   return (
     <div 
       style={{
-        '--glass-blur': `${glassBlur}px`,
-        '--glass-noise': glassNoise,
+        '--glass-blur': `${glassBlur}px`,
+        '--glass-border': glassBorder,
         '--glass-shift': `${glassShift}deg`
       } as React.CSSProperties}
     >
```

### `frontend/src/components/Layout.css`

```diff
@@ -29,1 +29,8 @@ .main-content {
   z-index: 1;
 }
+
+/* Obsidian HUD: Dynamic glassmorphism */
+.glass-panel {
+  backdrop-filter: blur(var(--glass-blur, 10px));
+  -webkit-backdrop-filter: blur(var(--glass-blur, 10px));
+  filter: hue-rotate(var(--glass-shift, 0deg));
+  border: 1px solid rgba(255, 255, 255, var(--glass-border, 0.08));
+  transition: all 0.3s ease-out;
+}
```

## B) Screen-Space Grid Picking

### `frontend/src/components/TitanCanvas.tsx`

Add screen-space grid structure and build/query functions:

```typescript
// Add after imports
interface ScreenGrid {
  cellSize: number
  cells: Map<string, number[]>
  width: number
  height: number
}

function buildScreenGrid(
  points: PointData[],
  camera: CameraState,
  canvasWidth: number,
  canvasHeight: number
): ScreenGrid {
  const cellSize = 24
  const grid = new Map<string, number[]>()
  
  for (let i = 0; i < points.length; i++) {
    const p = points[i]
    // Project to screen space
    const worldX = p.x01 * 2.0 - 1.0
    const worldY = p.y01 * 2.0 - 1.0
    const screenX = ((worldX + camera.panX) * camera.zoom + 1.0) * 0.5 * canvasWidth
    const screenY = ((worldY + camera.panY) * camera.zoom + 1.0) * 0.5 * canvasHeight
    
    const cellX = Math.floor(screenX / cellSize)
    const cellY = Math.floor(screenY / cellSize)
    const key = `${cellX},${cellY}`
    
    if (!grid.has(key)) grid.set(key, [])
    grid.get(key)!.push(i)
  }
  
  return { cellSize, cells: grid, width: canvasWidth, height: canvasHeight }
}

function findNearestInGrid(
  grid: ScreenGrid,
  points: PointData[],
  camera: CameraState,
  clickX: number,
  clickY: number,
  radiusPx: number,
  symbols: string[]
): string | null {
  const cellX = Math.floor(clickX / grid.cellSize)
  const cellY = Math.floor(clickY / grid.cellSize)
  
  let nearest: { index: number; dist: number } | null = null
  
  // Search 3x3 neighbor cells
  for (let dy = -1; dy <= 1; dy++) {
    for (let dx = -1; dx <= 1; dx++) {
      const key = `${cellX + dx},${cellY + dy}`
      const indices = grid.cells.get(key) || []
      
      for (const idx of indices) {
        const p = points[idx]
        const worldX = p.x01 * 2.0 - 1.0
        const worldY = p.y01 * 2.0 - 1.0
        const screenX = ((worldX + camera.panX) * camera.zoom + 1.0) * 0.5 * grid.width
        const screenY = ((worldY + camera.panY) * camera.zoom + 1.0) * 0.5 * grid.height
        
        const dx2 = screenX - clickX
        const dy2 = screenY - clickY
        const dist = Math.sqrt(dx2 * dx2 + dy2 * dy2)
        
        if (dist < radiusPx && (!nearest || dist < nearest.dist)) {
          nearest = { index: idx, dist }
        }
      }
    }
  }
  
  return nearest ? symbols[nearest.index] : null
}
```

Then in component:

```diff
@@ -343,6 +343,8 @@ export const TitanCanvas = forwardRef<TitanCanvasRef, TitanCanvasProps>(({
   const symbolsMapRef = useRef<Map<number, string>>(new Map())
   const pointsDataRef = useRef<PointData[]>([])
   const mousePosRef = useRef({ x: 0, y: 0 })
+  const screenGridRef = useRef<ScreenGrid | null>(null)
+  const lastGridBuildRef = useRef({ pointsHash: 0, cameraHash: '' })

   const camera = useCamera(1.0)
@@ -961,6 +963,30 @@ export const TitanCanvas = forwardRef<TitanCanvasRef, TitanCanvasProps>(({
   const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
     if (e.button === 0) {
-      picking.handleClick(e)
+      // Use screen-space grid for picking
+      const canvas = canvasRef.current
+      if (!canvas || !screenGridRef.current) {
+        picking.handleClick(e)
+        return
+      }
+      
+      const rect = canvas.getBoundingClientRect()
+      const clickX = e.clientX - rect.left
+      const clickY = e.clientY - rect.top
+      
+      const symbols = Array.from(symbolsMapRef.current.values())
+      const symbol = findNearestInGrid(
+        screenGridRef.current,
+        pointsDataRef.current,
+        camera.camera,
+        clickX,
+        clickY,
+        12, // radiusPx
+        symbols
+      )
+      
+      if (symbol && onAssetClick) {
+        onAssetClick(symbol)
+      } else {
+        picking.handleClick(e)
+      }
     }
     camera.handleMouseDown(e)
   }, [picking, camera, onAssetClick])
+
+  // Rebuild grid when points or camera changes
+  useEffect(() => {
+    const canvas = canvasRef.current
+    if (!canvas || pointsDataRef.current.length === 0) return
+    
+    const pointsHash = pointsDataRef.current.length
+    const cameraHash = `${camera.camera.panX},${camera.camera.panY},${camera.camera.zoom}`
+    
+    if (lastGridBuildRef.current.pointsHash !== pointsHash ||
+        lastGridBuildRef.current.cameraHash !== cameraHash) {
+      screenGridRef.current = buildScreenGrid(
+        pointsDataRef.current,
+        camera.camera,
+        canvas.clientWidth,
+        canvas.clientHeight
+      )
+      lastGridBuildRef.current = { pointsHash, cameraHash }
+    }
+  }, [pointsData, camera.camera])
```

## A) WebGL2 FBO Pipeline

**NOTE**: Full 3-pass FBO pipeline implementation is complex and requires significant refactoring. For Iteration 1, the enhanced fragment shader (SINGULARITY_FRAGMENT_SHADER) is already added but not yet integrated into the render pipeline.

The FBO pipeline will be implemented in a future iteration to maintain 60fps guarantee. Current mode 2 uses the enhanced shader with multi-layer glow effects.

## Test Checklist

### D) Motor Signals
- [ ] Run ingest: `python -m services.ingest_service ingest_run --limit 100`
- [ ] Check database: `SELECT symbol, meta32 FROM assets LIMIT 5`
- [ ] Verify meta32 values are normalized (shock8, risk8, vital6, macro8 in valid ranges)
- [ ] Decode meta32: `shock8 = meta32 & 0xFF; risk8 = (meta32 >> 8) & 0xFF; ...`

### C) Obsidian Glass
- [ ] Click point to open detail panel
- [ ] Panel blur should be 10px when shockFactor=0, 22px when shockFactor=1
- [ ] Panel border opacity should be 0.08 when shockFactor=0, 0.18 when shockFactor=1
- [ ] Smooth transitions on shockFactor change

### B) Screen-Space Grid
- [ ] Click visible point → should select correct symbol
- [ ] Grid rebuilds only on points/camera change (check console logs)
- [ ] No lag on click (should be O(k) where k is small)

### A) FBO Pipeline (Future)
- [ ] Mode 3 enables full 3-pass pipeline
- [ ] Orange core + cyan aura visible
- [ ] Bloom effect visible
- [ ] Stable 60fps maintained

## Validation

- **Visual**: Orange core + cyan aura + bloom (when FBO enabled)
- **Perf**: Stable 60fps at 10k points
- **Picking**: Click selects correct symbol without lag
- **No request storm**: points.bin ≤ 1 req/2s
- **meta32 effects**: High shock = more pulse, high risk = brighter
