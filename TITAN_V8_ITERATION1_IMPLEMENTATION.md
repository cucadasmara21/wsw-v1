# Titan V8 Iteration 1 - Implementation Plan

## Overview
Implementing WebGL2 FBO pipeline, screen-space grid picking, Obsidian Glass, and real motor signals for meta32.

## A) WebGL2 "Luminous Singularity" (MULTIPASS FBO)

### Shaders to Add

#### Aura Pass Fragment Shader
```glsl
#version 300 es
precision highp float;
in vec4 v_color;
uniform float u_time;
uniform float u_risk;
uniform float u_shock;
uniform float u_vital;
out vec4 outColor;

void main() {
  vec2 uv = gl_PointCoord * 2.0 - 1.0;
  float r2 = dot(uv, uv);
  if (r2 > 1.0) discard;
  
  // Inner core: burning orange (k_core ~ 25)
  float k_core = 25.0;
  float core = exp(-r2 * k_core);
  vec3 coreColor = vec3(1.0, 0.4, 0.0) * (0.8 + 0.4 * u_risk);
  
  // Outer aura: cyan (k_aura ~ 8)
  float k_aura = 8.0;
  float aura = exp(-r2 * k_aura) * (1.0 - core * 0.5);
  vec3 auraColor = vec3(0.0, 1.0, 1.0) * (0.6 + 0.4 * u_risk);
  
  // Shock-modulated pulse
  float pulse = 1.0 + sin(u_time * 3.0) * u_shock * 0.1;
  
  vec3 color = (coreColor * core + auraColor * aura) * pulse;
  float alpha = v_color.a * smoothstep(1.0, 0.0, r2);
  outColor = vec4(color, alpha);
}
```

#### Blur Shader (Separable, 9 taps)
```glsl
#version 300 es
precision highp float;
uniform sampler2D u_texture;
uniform vec2 u_texelSize;
uniform vec2 u_dir; // (1,0) or (0,1)
in vec2 v_texCoord;
out vec4 outColor;

void main() {
  vec4 color = vec4(0.0);
  float weights[9] = float[](
    0.01621622, 0.05405405, 0.12162162, 0.19459459,
    0.22702703,
    0.19459459, 0.12162162, 0.05405405, 0.01621622
  );
  float offsets[9] = float[](-4.0, -3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0);
  
  for (int i = 0; i < 9; i++) {
    vec2 offset = u_dir * offsets[i] * u_texelSize;
    color += texture(u_texture, v_texCoord + offset) * weights[i];
  }
  outColor = color;
}
```

#### Composite Shader
```glsl
#version 300 es
precision highp float;
uniform sampler2D u_baseTex;
uniform sampler2D u_auraTex;
uniform sampler2D u_bloomTex;
in vec2 v_texCoord;
out vec4 outColor;

void main() {
  vec4 base = texture(u_baseTex, v_texCoord);
  vec4 aura = texture(u_auraTex, v_texCoord);
  vec4 bloom = texture(u_bloomTex, v_texCoord);
  
  // Additive compositing
  outColor = base + aura * 1.2 + bloom * 0.8;
  outColor.a = 1.0;
}
```

### FBO Utilities
- `createTexture(gl, w, h, format)`: Create RGBA8 texture
- `createFBO(gl, texture)`: Create framebuffer with texture attachment
- `createFullscreenQuad(gl)`: VAO for fullscreen quad rendering

### Render Pipeline (mode 3 = Singularity)
1. **Pass 0 (Base)**: Render points to `baseTex` (existing shader)
2. **Pass 1 (Aura)**: Render points to `auraTex` with additive blend (ONE, ONE)
3. **Pass 2 (Blur H)**: Blur `auraTex` horizontally → `blurPing`
4. **Pass 3 (Blur V)**: Blur `blurPing` vertically → `blurPong` (half-res)
5. **Pass 4 (Composite)**: Draw fullscreen quad: base + aura + bloom

## B) Screen-Space Grid Picking

### Grid Structure
```typescript
interface ScreenGrid {
  cellSize: number // 24px
  cells: Map<string, number[]> // "x,y" -> [indices]
  width: number
  height: number
}
```

### Build Grid (on points/camera change)
```typescript
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
    const screenX = ((p.x01 * 2.0 - 1.0 + camera.panX) * camera.zoom + 1.0) * 0.5 * canvasWidth
    const screenY = ((p.y01 * 2.0 - 1.0 + camera.panY) * camera.zoom + 1.0) * 0.5 * canvasHeight
    
    const cellX = Math.floor(screenX / cellSize)
    const cellY = Math.floor(screenY / cellSize)
    const key = `${cellX},${cellY}`
    
    if (!grid.has(key)) grid.set(key, [])
    grid.get(key)!.push(i)
  }
  
  return { cellSize, cells: grid, width: canvasWidth, height: canvasHeight }
}
```

### Click Handler
```typescript
function handleClick(e: MouseEvent, grid: ScreenGrid, points: PointData[], symbols: string[]) {
  const rect = canvas.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  
  const cellX = Math.floor(x / grid.cellSize)
  const cellY = Math.floor(y / grid.cellSize)
  const radiusPx = 12
  
  let nearest: { index: number; dist: number } | null = null
  
  // Search 3x3 neighbor cells
  for (let dy = -1; dy <= 1; dy++) {
    for (let dx = -1; dx <= 1; dx++) {
      const key = `${cellX + dx},${cellY + dy}`
      const indices = grid.cells.get(key) || []
      
      for (const idx of indices) {
        const p = points[idx]
        const screenX = ((p.x01 * 2.0 - 1.0 + camera.panX) * camera.zoom + 1.0) * 0.5 * canvasWidth
        const screenY = ((p.y01 * 2.0 - 1.0 + camera.panY) * camera.zoom + 1.0) * 0.5 * canvasHeight
        
        const dx2 = screenX - x
        const dy2 = screenY - y
        const dist = Math.sqrt(dx2 * dx2 + dy2 * dy2)
        
        if (dist < radiusPx && (!nearest || dist < nearest.dist)) {
          nearest = { index: idx, dist }
        }
      }
    }
  }
  
  if (nearest && onAssetClick) {
    onAssetClick(symbols[nearest.index])
  }
}
```

## C) Obsidian Glass HUD

### CSS Variables (in UniversePage)
```typescript
const glassBlur = lerp(10, 22, shockFactor) // 10px to 22px
const glassBorder = lerp(0.08, 0.18, shockFactor) // opacity

<div style={{
  '--glass-blur': `${glassBlur}px`,
  '--glass-border': glassBorder
} as React.CSSProperties}>
```

### CSS Class
```css
.glass-panel {
  backdrop-filter: blur(var(--glass-blur, 10px));
  border: 1px solid rgba(255, 255, 255, var(--glass-border, 0.08));
  transition: all 0.3s ease-out;
}
```

## D) Motor Signals -> meta32

### Normalization Function
```python
def normalize_signal(x: float, k: float = 1.0) -> float:
    """Normalize signal: norm(x) = 0.5 + 0.5*tanh(x/k)"""
    import math
    return 0.5 + 0.5 * math.tanh(x / k)
```

### Compute Real Signals
```python
async def _compute_asset_metrics(symbol: str, domain_id: int, macro_scalar: float) -> Dict:
    # TODO: Fetch real bars/history for symbol
    # For now, use deterministic hash-based signals with normalization
    
    # Shock: CUSUM magnitude or jump z-score
    # shock_raw = compute_cusum_magnitude(bars) or compute_jump_zscore(bars)
    # shock = normalize_signal(shock_raw, k=2.0)
    shock = normalize_signal(_u01_from_hash(_hash_symbol(symbol + "shock")) * 4.0 - 2.0, k=2.0)
    
    # Risk: composite (vol + liquidity + drift)
    # risk_raw = compute_volatility(bars) * 0.4 + compute_liquidity(bars) * 0.3 + compute_drift(bars) * 0.3
    # risk = normalize_signal(risk_raw, k=1.5)
    risk = normalize_signal(_u01_from_hash(_hash_symbol(symbol + "risk")) * 3.0 - 1.5, k=1.5)
    
    # Trend: RLS slope / regime (0=flat, 1=bull, 2=bear)
    # slope = compute_rls_slope(bars)
    # trend = 0 if abs(slope) < 0.01 else (1 if slope > 0 else 2)
    momentum = (_u01_from_hash(_hash_symbol(symbol + "trend")) - 0.5) * 0.4
    trend = 0 if abs(momentum) < 0.05 else (1 if momentum > 0 else 2)
    
    # Vital: data completeness / liquidity
    # vital_raw = compute_data_completeness(bars) * 0.6 + compute_liquidity_score(bars) * 0.4
    # vital = normalize_signal(vital_raw, k=1.0)
    liq = _u01_from_hash(_hash_symbol(symbol + "liq"))
    vital = normalize_signal(liq * 2.0 - 1.0, k=1.0)
    
    # Macro: normalized macro pressure (from FRED cache)
    macro = normalize_signal(macro_scalar * 2.0 - 1.0, k=1.0)
    
    # Pack into meta32
    shock8 = int(round(shock * 255.0)) & 0xFF
    risk8 = int(round(risk * 255.0)) & 0xFF
    trend2 = int(trend) & 0x03
    vital6 = int(round(vital * 63.0)) & 0x3F
    macro8 = int(round(macro * 255.0)) & 0xFF
    
    meta32 = shock8 | (risk8 << 8) | (trend2 << 16) | (vital6 << 18) | (macro8 << 24)
    
    # ... rest of function
```

## Implementation Order

1. **D) Motor Signals** - Update `services/ingest_service.py` with normalization
2. **C) Obsidian Glass** - Enhance CSS variables in `UniversePage.tsx`
3. **B) Screen-Space Grid** - Add grid building and click handler in `TitanCanvas.tsx`
4. **A) FBO Pipeline** - Add shaders and render passes (behind mode 3 flag)

## Validation

- Visual: Orange core + cyan aura + bloom visible
- Perf: Stable 60fps at 10k points
- Picking: Click selects correct symbol without lag
- No request storm regressions
- meta32 values affect pulse/brightness (high shock = more pulse, high risk = brighter)
