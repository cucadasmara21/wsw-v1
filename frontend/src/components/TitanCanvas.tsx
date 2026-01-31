import { useEffect, useRef, useState, useImperativeHandle, forwardRef, useCallback, useMemo } from 'react'
import { useCamera, type CameraState } from '../hooks/useCamera'
import { usePointPicking, type PointData } from '../hooks/usePointPicking'
import { usePointData } from '../hooks/usePointData'
import { PointTooltip } from './PointTooltip'
import { AssetDetailPanel } from './AssetDetailPanel'
import { TITAN_V8_VERTEX_SHADER, TITAN_V8_FRAGMENT_SHADER, PICKING_VERTEX_SHADER, PICKING_FRAGMENT_SHADER } from '../render/quantumShaders'
import { ZstdCodec } from 'zstd-codec'
import { validateVertex28Buffer } from '../lib/vertex28Validation'

export interface TitanCanvasRef {
  refresh: () => void
  focusPoint: (point: PointData) => void
}

interface TitanCanvasProps {
  pointSize?: number
  glowStrength?: number
  pollMs?: number
  riskMin?: number
  shockMin?: number
  trendFilter?: Set<number>
  onHover?: (point: PointData | null) => void
  onSelect?: (point: PointData | null) => void
  onAssetClick?: (symbol: string) => void
  onPick?: (point: PointData | null) => void
}

const DEBUG_POLL = true

const VERTEX28_STRIDE = 28

let _zstdInit: Promise<any> | null = null
let _zstdSimple: any | null = null

async function _getZstdSimple(): Promise<any> {
  if (_zstdSimple) return _zstdSimple
  if (_zstdInit) return _zstdInit
  _zstdInit = new Promise((resolve) => {
    ZstdCodec.run((zstd: any) => {
      _zstdSimple = new zstd.Simple()
      resolve(_zstdSimple)
    })
  })
  return _zstdInit
}

async function decompressZstdArrayBuffer(ab: ArrayBuffer): Promise<ArrayBuffer> {
  const simple = await _getZstdSimple()
  const out: Uint8Array = simple.decompress(new Uint8Array(ab))
  return out.buffer.slice(out.byteOffset, out.byteOffset + out.byteLength)
}

// Vertex28 offsets (Route A): <IIfffff = morton_u32, meta32_u32, x,y,z,risk,shock
const V28_OFF_MORTON = 0
const V28_OFF_META = 4
const V28_OFF_X = 8
const V28_OFF_Y = 12
const V28_OFF_Z = 16
const V28_OFF_RISK = 20
const V28_OFF_SHOCK = 24

// Web Worker for screen-space grid picking (inline blob)
const PICKING_WORKER_CODE = `
const CELL_SIZE = 24;
let gridBins = new Map();
let screenPositions = null;

self.onmessage = function(e) {
  const { type, data } = e.data;
  
  if (type === 'build') {
    const { positions, width, height } = data;
    const n = positions.length / 2;
    console.debug('[worker<-msg] type=build, positionsLen=', positions.length, 'count=', n);
    screenPositions = positions;
    gridBins.clear();
    for (let i = 0; i < n; i++) {
      const x = positions[i * 2];
      const y = positions[i * 2 + 1];
      const cellX = Math.floor(x / CELL_SIZE);
      const cellY = Math.floor(y / CELL_SIZE);
      const key = (cellX << 16) | (cellY & 0xFFFF);
      
      if (!gridBins.has(key)) {
        gridBins.set(key, []);
      }
      gridBins.get(key).push(i);
    }
    
    self.postMessage({ type: 'built' });
  } else if (type === 'query') {
    const { x, y, radiusPx } = data;
    if (!screenPositions) {
      self.postMessage({ type: 'result', index: -1 });
      return;
    }
    
    const cellX = Math.floor(x / CELL_SIZE);
    const cellY = Math.floor(y / CELL_SIZE);
    const radius2 = radiusPx * radiusPx;
    
    let nearestIdx = -1;
    let minDist2 = radius2;
    
    for (let dy = -1; dy <= 1; dy++) {
      for (let dx = -1; dx <= 1; dx++) {
        const key = ((cellX + dx) << 16) | ((cellY + dy) & 0xFFFF);
        const indices = gridBins.get(key) || [];
        
        for (const idx of indices) {
          const px = screenPositions[idx * 2];
          const py = screenPositions[idx * 2 + 1];
          const dx2 = px - x;
          const dy2 = py - y;
          const dist2 = dx2 * dx2 + dy2 * dy2;
          
          if (dist2 < minDist2) {
            minDist2 = dist2;
            nearestIdx = idx;
          }
        }
      }
    }
    
    self.postMessage({ type: 'result', index: nearestIdx });
  }
};
`

function createPickingWorker(): Worker | null {
  try {
    const blob = new Blob([PICKING_WORKER_CODE], { type: 'application/javascript' })
    const url = URL.createObjectURL(blob)
    const worker = new Worker(url)
    URL.revokeObjectURL(url)
    return worker
  } catch (err) {
    console.warn('Failed to create picking worker, falling back to main thread:', err)
    return null
  }
}

const DEBUG_VERTEX_SHADER = `#version 300 es
precision highp float;

out vec4 v_color;

void main() {
  vec2 pos[3];
  pos[0] = vec2(-0.5, 0.0);
  pos[1] = vec2(0.0, 0.0);
  pos[2] = vec2(0.5, 0.0);
  
  gl_Position = vec4(pos[gl_VertexID], 0.0, 1.0);
  gl_PointSize = 24.0;
  v_color = vec4(1.0, 1.0, 1.0, 1.0);
}
`

// Route A: legacy shaders removed (Vertex28-only)

const SINGULARITY_FRAGMENT_SHADER = `#version 300 es
precision highp float;

in vec4 v_color;
uniform float u_time;
uniform float u_shock;
uniform float u_risk;

out vec4 outColor;

void main() {
  vec2 uv = gl_PointCoord * 2.0 - 1.0;
  float r2 = dot(uv, uv);
  if (r2 > 1.0) discard;

  float k_core = 25.0;
  float core = exp(-r2 * k_core);
  vec3 coreColor = vec3(1.0, 0.4, 0.0) * (0.8 + 0.4 * u_risk);
  
  float k_aura = 8.0;
  float aura = exp(-r2 * k_aura) * (1.0 - core * 0.5);
  vec3 auraColor = vec3(0.0, 1.0, 1.0) * (0.6 + 0.4 * u_risk);
  
  float pulse = 1.0 + sin(u_time * 3.0) * u_shock * 0.1;
  
  vec3 color = (coreColor * core + auraColor * aura) * pulse;
  float alpha = v_color.a * smoothstep(1.0, 0.0, r2);
  
  outColor = vec4(color, alpha);
}
`

// Bloom multipass shaders
const BLUR_VERTEX_SHADER = `#version 300 es
precision highp float;

in vec2 a_position;
out vec2 v_texCoord;

void main() {
  v_texCoord = a_position * 0.5 + 0.5;
  gl_Position = vec4(a_position, 0.0, 1.0);
}
`

const BLUR_FRAGMENT_SHADER = `#version 300 es
precision highp float;

in vec2 v_texCoord;
uniform sampler2D u_texture;
uniform vec2 u_texelSize;
uniform vec2 u_direction;
out vec4 outColor;

void main() {
  vec4 color = texture(u_texture, v_texCoord) * 0.2270270270;
  color += texture(u_texture, v_texCoord + u_texelSize * u_direction * 1.3846153846) * 0.3162162162;
  color += texture(u_texture, v_texCoord - u_texelSize * u_direction * 1.3846153846) * 0.3162162162;
  color += texture(u_texture, v_texCoord + u_texelSize * u_direction * 3.2307692308) * 0.0702702703;
  color += texture(u_texture, v_texCoord - u_texelSize * u_direction * 3.2307692308) * 0.0702702703;
  outColor = color;
}
`

const COMPOSITE_VERTEX_SHADER = `#version 300 es
precision highp float;

in vec2 a_position;
out vec2 v_texCoord;

void main() {
  v_texCoord = a_position * 0.5 + 0.5;
  gl_Position = vec4(a_position, 0.0, 1.0);
}
`

const COMPOSITE_FRAGMENT_SHADER = `#version 300 es
precision highp float;

in vec2 v_texCoord;
uniform sampler2D u_baseTexture;
uniform sampler2D u_bloomTexture;
uniform float u_singularityIntensity;
out vec4 outColor;

void main() {
  vec4 base = texture(u_baseTexture, v_texCoord);
  vec4 bloom = texture(u_bloomTexture, v_texCoord);
  
  vec3 coreColor = vec3(1.0, 0.4, 0.0) * u_singularityIntensity;
  vec3 composite = base.rgb + bloom.rgb * (0.5 + 0.5 * u_singularityIntensity) + coreColor * u_singularityIntensity * 0.3;
  
  outColor = vec4(composite, base.a);
}
`

const FULLSCREEN_QUAD = new Float32Array([
  -1.0, -1.0,
   1.0, -1.0,
  -1.0,  1.0,
   1.0,  1.0
])

function assertWebGL2(gl: WebGLRenderingContext | WebGL2RenderingContext | null): asserts gl is WebGL2RenderingContext {
  if (!gl || !(gl instanceof WebGL2RenderingContext)) {
    throw new Error("WebGL2 required")
  }
}

function compile(gl: WebGL2RenderingContext, type: number, src: string): WebGLShader {
  const sh = gl.createShader(type)
  if (!sh) {
    throw new Error("Failed to create shader")
  }
  gl.shaderSource(sh, src)
  gl.compileShader(sh)
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(sh) || "Unknown error"
    gl.deleteShader(sh)
    throw new Error(`Shader compile error: ${log}`)
  }
  return sh
}

function link(gl: WebGL2RenderingContext, vsSrc: string, fsSrc: string): WebGLProgram {
  const vs = compile(gl, gl.VERTEX_SHADER, vsSrc)
  const fs = compile(gl, gl.FRAGMENT_SHADER, fsSrc)
  const prog = gl.createProgram()
  if (!prog) {
    throw new Error("Failed to create program")
  }
  gl.attachShader(prog, vs)
  gl.attachShader(prog, fs)
  gl.linkProgram(prog)
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    const log = gl.getProgramInfoLog(prog) || "Unknown error"
    gl.deleteProgram(prog)
    gl.deleteShader(vs)
    gl.deleteShader(fs)
    throw new Error(`Program link error: ${log}`)
  }
  gl.deleteShader(vs)
  gl.deleteShader(fs)
  return prog
}

function setCommonGLState(gl: WebGL2RenderingContext) {
  gl.enable(gl.BLEND)
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
  gl.enable(gl.PROGRAM_POINT_SIZE)
  gl.disable(gl.DEPTH_TEST)
  gl.disable(gl.CULL_FACE)
}

// Route A: legacy (uint16) buffers removed.

export const TitanCanvas = forwardRef<TitanCanvasRef, TitanCanvasProps>(({
  pointSize = 10.0,
  glowStrength = 1.0,
  pollMs = 500,
  riskMin = 0,
  shockMin = 0,
  trendFilter = new Set([0, 1, 2, 3, 4, 5, 6, 7]),
  onHover,
  onSelect,
  onAssetClick,
  onPick
}, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const glRef = useRef<WebGL2RenderingContext | null>(null)
  const programRef = useRef<WebGLProgram | null>(null)
  const debugProgramRef = useRef<WebGLProgram | null>(null)
  const singularityProgramRef = useRef<WebGLProgram | null>(null)
  const enableSingularityRef = useRef(false)
  const bufferRef = useRef<WebGLBuffer | null>(null)
  const vaoRef = useRef<WebGLVertexArrayObject | null>(null)
  const vertexCountRef = useRef(0)
  const timeRef = useRef(0)
  const renderLoopRef = useRef<number | null>(null)
  const fpsRef = useRef({ frames: 0, lastTime: 0, fps: 60 })
  const frameTimeRef = useRef(0)
  const inFlightRef = useRef(false)
  const pollTimerRef = useRef<number | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const symbolsLoadedRef = useRef(false)
  const pollEpochRef = useRef(0)
  const lastStartMsRef = useRef(0)
  const pollOnceRef = useRef<(() => Promise<void>) | null>(null)
  const instanceIdRef = useRef(Math.random().toString(16).slice(2))
  const pointSizeRef = useRef(Math.max(2.0, pointSize))
  const modeRef = useRef(2)
  const debugForceRef = useRef(false)
  const canvasWidthRef = useRef(0)
  const canvasHeightRef = useRef(0)
  const dprRef = useRef(1)
  const programLinkOkRef = useRef(false)
  const debugProgramLinkOkRef = useRef(false)
  const vaoBoundRef = useRef(false)
  const lastGLErrorRef = useRef<number | null>(null)
  const lastGLErrorNameRef = useRef<string>('NO_ERROR')
  const shaderLogRef = useRef<string | null>(null)
  const drawnCountRef = useRef(0)
  const viewportWidthRef = useRef(0)
  const viewportHeightRef = useRef(0)
  const boundsRef = useRef<Bounds>({
    minX: 0,
    maxX: 0,
    minY: 0,
    maxY: 0,
    uniqueX: 0,
    uniqueY: 0,
    degenerate: false
  })
  const bufferDataRef = useRef<ArrayBuffer | null>(null)
  const symbolsMapRef = useRef<Map<number, string>>(new Map())
  const pointsDataRef = useRef<PointData[]>([])
  const globalShockFactorRef = useRef(0.0)
  const pickingWorkerRef = useRef<Worker | null>(null)
  const onAssetClickRef = useRef(onAssetClick)
  const screenPositionsRef = useRef<Float32Array | null>(null)
  const lastGridBuildRef = useRef<{ pointsHash: number; cameraHash: number } | null>(null)
  const mousePosRef = useRef({ x: 0, y: 0 })

  const camera = useCamera(1.0)
  const [stats, setStats] = useState({
    points: 0,
    bytes: 0,
    stride: 12,
    noData: false,
    fetchMs: 0,
    xMin: 0,
    xMax: 0,
    yMin: 0,
    yMax: 0,
    xyDegen: false,
    uniqueX512: 0,
    uniqueY512: 0,
    dataDegenerateFallback: false,
    fps: 60,
    frameTime: 0,
    canvasW: 0,
    canvasH: 0,
    canvasClientW: 0,
    canvasClientH: 0,
    dpr: 1,
    viewportW: 0,
    viewportH: 0,
    drawn: 0,
    glError: 0,
    glErrorName: 'NO_ERROR',
    programLink: false,
    debugProgramLink: false,
    vaoBound: false,
    shaderLog: null as string | null,
    mode: 2,
    debugForce: false
  })

  // V8 state
  const useV8Ref = useRef(true) // Route A: always true
  const v8BackoffUntilRef = useRef(0)
  const v8NextRetryAtRef = useRef<number>(0)
  const v8TypedArraysRef = useRef<{
    positions: Float32Array | null
    risk: Float32Array | null
    shock: Float32Array | null
    morton: Uint32Array | null
    meta32: Uint32Array | null
    count: number
  }>({
    positions: null,
    risk: null,
    shock: null,
    morton: null,
    meta32: null,
    count: 0
  })
  const pickingFramebufferRef = useRef<WebGLFramebuffer | null>(null)
  const pickingTextureRef = useRef<WebGLTexture | null>(null)
  const pickingProgramRef = useRef<WebGLProgram | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const deltaQueueRef = useRef<ArrayBuffer[]>([])
  const quantumStatsRef = useRef({
    assetCount: 0,
    stride: 28,
    snapshotBytes: 0,
    decompressMs: 0,
    parseMs: 0,
    fps: 60,
    deltaQueueDepth: 0,
    lastWSLagMs: 0
  })

  const pointsData = pointsDataRef.current
  const picking = usePointPicking(pointsData, camera.camera, pointSizeRef.current)

  // Track pointsCount/hasPositions changes (avoid per-frame spam)
  const lastPointsCountRef = useRef(0)
  const lastHasPositionsRef = useRef(false)
  useEffect(() => {
    const pointsCount = pointsData.length
    const hasPositions = !!screenPositionsRef.current
    if (pointsCount !== lastPointsCountRef.current || hasPositions !== lastHasPositionsRef.current) {
      console.debug('[points] pointsCount=', pointsCount, 'hasPositions=', hasPositions)
      lastPointsCountRef.current = pointsCount
      lastHasPositionsRef.current = hasPositions
    }
  }, [pointsData.length])

  useImperativeHandle(ref, () => ({
    refresh: () => {
      // Trigger poller's pollOnce function (respects all guards)
      if (pollOnceRef.current) {
        void pollOnceRef.current()
      }
    },
    focusPoint: (point: PointData) => {
      const worldX = point.x01 * 2.0 - 1.0
      const worldY = point.y01 * 2.0 - 1.0
      camera.focus(worldX, worldY, 2.0)
    }
  }))

  const clearPollTimer = useCallback(() => {
    if (pollTimerRef.current != null) {
      window.clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  // Route A: legacy 12-byte pipeline removed

  // Route A: no pipeline rebuild (V8-only)

  // Route A: Vertex28 only. Supports compression=zstd (default) and compression=none for debugging.

  // V8: Parse Vertex28 format
  const parseVertex28 = (buffer: ArrayBuffer): {
    positions: Float32Array
    risk: Float32Array
    shock: Float32Array
    morton: Uint32Array
    meta32: Uint32Array
    count: number
  } => {
    const parseStart = performance.now()
    const bytes = new Uint8Array(buffer)
    const count = Math.floor(bytes.length / VERTEX28_STRIDE)
    
    // Pre-allocate typed arrays (zero-copy strategy)
    const positions = new Float32Array(count * 3)
    const risk = new Float32Array(count)
    const shock = new Float32Array(count)
    const morton = new Uint32Array(count)
    const meta32 = new Uint32Array(count)
    
    const view = new DataView(buffer)
    for (let i = 0; i < count; i++) {
      const offset = i * VERTEX28_STRIDE
      if (offset + 28 > buffer.byteLength) {
        throw new Error('FAIL_FAST: VERTEX28_BOUNDS')
      }
      morton[i] = view.getUint32(offset + V28_OFF_MORTON, true) // little-endian
      meta32[i] = view.getUint32(offset + V28_OFF_META, true)
      positions[i * 3] = view.getFloat32(offset + V28_OFF_X, true)
      positions[i * 3 + 1] = view.getFloat32(offset + V28_OFF_Y, true)
      positions[i * 3 + 2] = view.getFloat32(offset + V28_OFF_Z, true)
      risk[i] = view.getFloat32(offset + V28_OFF_RISK, true)
      shock[i] = view.getFloat32(offset + V28_OFF_SHOCK, true)
    }
    
    const parseMs = Math.round(performance.now() - parseStart)
    quantumStatsRef.current.parseMs = parseMs
    
    return { positions, risk, shock, morton, meta32, count }
  }

  const v8Compression = (() => {
    // Default Route A: zstd. Allow debugging with ?v8Compression=none
    try {
      const p = new URLSearchParams(window.location.search).get('v8Compression')
      return p === 'none' ? 'none' : 'zstd'
    } catch {
      return 'zstd'
    }
  })()
  // V8: Fetch snapshot (Route A / Vertex28)
  // - Fail-fast on contract violations (stride != 28, byteLength % 28 != 0)
  // - 503 => backoff + keep last known good VBO
  // - On non-503 errors => surface in shaderLog, but DO NOT clear current VBO
  const fetchV8Snapshot = async (signal?: AbortSignal): Promise<boolean> => {
    const g = glRef.current
    const vbo = bufferRef.current

    // Local helpers (kept inside to avoid file-wide noise)
    const computeBoundsFromPositions = (pos: Float32Array, count: number) => {
      let minX = Number.POSITIVE_INFINITY
      let maxX = Number.NEGATIVE_INFINITY
      let minY = Number.POSITIVE_INFINITY
      let maxY = Number.NEGATIVE_INFINITY

      for (let i = 0; i < count; i++) {
        const x = pos[i * 3]
        const y = pos[i * 3 + 1]
        if (!Number.isFinite(x) || !Number.isFinite(y)) continue
        if (x < minX) minX = x
        if (x > maxX) maxX = x
        if (y < minY) minY = y
        if (y > maxY) maxY = y
      }

      // Fallback if degenerate/invalid
      if (!Number.isFinite(minX) || !Number.isFinite(maxX) || minX === maxX) {
        minX = -1
        maxX = 1
      }
      if (!Number.isFinite(minY) || !Number.isFinite(maxY) || minY === maxY) {
        minY = -1
        maxY = 1
      }

      return { minX, maxX, minY, maxY, degenerate: (minX === maxX) || (minY === maxY) }
    }

    try {
      const url = `/api/universe/v8/snapshot?format=vertex28&compression=${v8Compression}`
      const fetchStart = performance.now()

      const resp = await fetch(url, { signal })

      if (resp.status === 503) {
        // Backend temporary unavailable — keep last good VBO
        console.warn('[V8] snapshot 503: backend unavailable')
        setStats(prev => ({ ...prev, shaderLog: 'V8 snapshot unavailable (503). Retrying…' }))
        v8NextRetryAtRef.current = Date.now() + 5000
        return false
      }

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`)
      }

      const stride = resp.headers.get('x-wsw-stride') ?? resp.headers.get('X-Vertex-Stride')
      const fmt = resp.headers.get('x-wsw-format') ?? resp.headers.get('X-WSW-Format')
      const contentEnc = (resp.headers.get('content-encoding') ?? '').toLowerCase()

      if (stride !== '28') {
        throw new Error(`Vertex28 contract violation: header stride=${stride ?? 'null'} (expected 28)`)
      }
      if (fmt && fmt.toLowerCase() !== 'vertex28') {
        throw new Error(`Vertex28 contract violation: header format=${fmt} (expected vertex28)`)
      }

      const rawBuf = await resp.arrayBuffer()
      const rawBytes = rawBuf.byteLength
      const wantsZstd = v8Compression === 'zstd'
      const serverZstd = contentEnc === 'zstd'

      // Decompression policy (resilient):
      // - Try zstd if either requested or server claims zstd.
      // - Prefer decompressed buffer if it validates Vertex28.
      // - Otherwise fall back to raw buffer if it validates Vertex28.
      // - Fail only if neither validates Vertex28.
      let buf: ArrayBuffer | null = null
      let decompressMs = 0
      let decompressed: ArrayBuffer | null = null

      if (wantsZstd || serverZstd) {
        const t0 = performance.now()
        try {
          decompressed = await decompressZstdArrayBuffer(rawBuf)
        } catch (e) {
          decompressed = null
        }
        decompressMs = Math.round(performance.now() - t0)
      }

      const rawOk = rawBuf.byteLength > 0 && (rawBuf.byteLength % VERTEX28_STRIDE === 0)
      const decOk = !!decompressed && decompressed.byteLength > 0 && (decompressed.byteLength % VERTEX28_STRIDE === 0)

      if (decOk) {
        buf = decompressed as ArrayBuffer
      } else if (rawOk) {
        if (serverZstd) {
          console.warn('[V8] content-encoding=zstd but decompression failed/invalid; using raw buffer', { rawBytes, decBytes: (decompressed?.byteLength ?? 0) })
        }
        buf = rawBuf
        decompressMs = 0
      } else {
        throw new Error(`Vertex28 contract violation: rawBytes=${rawBuf.byteLength}, decBytes=${decompressed?.byteLength ?? 0}, wantsZstd=${wantsZstd}, serverZstd=${serverZstd}`)
      }

      validateVertex28Buffer(buf)

      // Parse Vertex28 immediately after decompression
      const parsed = parseVertex28(buf)

      if (parsed.count <= 0) {
        throw new Error('Parsed snapshot contains 0 points.')
      }

      // Update bounds (for shader normalization) BEFORE rendering
      const b = computeBoundsFromPositions(parsed.positions, parsed.count)
      boundsRef.current = {
        ...boundsRef.current,
        minX: b.minX,
        maxX: b.maxX,
        minY: b.minY,
        maxY: b.maxY,
        degenerate: b.degenerate
      }

      // Build PointData[] for picking/interaction
      const dx = Math.max(1e-9, (boundsRef.current.maxX - boundsRef.current.minX))
      const dy = Math.max(1e-9, (boundsRef.current.maxY - boundsRef.current.minY))

      const pts: PointData[] = new Array(parsed.count)
      for (let i = 0; i < parsed.count; i++) {
        const x = parsed.positions[i * 3]
        const y = parsed.positions[i * 3 + 1]
        const z = parsed.positions[i * 3 + 2]

        const x01 = (x - boundsRef.current.minX) / dx
        const y01 = (y - boundsRef.current.minY) / dy

        const symbol = symbolsMapRef.current.get(i) ?? `AST${String(i).padStart(6, '0')}`

        pts[i] = {
          index: i,
          x01: Math.min(1, Math.max(0, x01)),
          y01: Math.min(1, Math.max(0, y01)),
          z,
          risk: parsed.risk[i],
          shock: parsed.shock[i],
          trend: 0,
          vital: 0,
          macro: 0,
          symbol,
          assetId: i
        }
      }

      // Upload buffer to GPU (MANDATORY)
      if (g && vbo) {
        g.bindBuffer(g.ARRAY_BUFFER, vbo)
        g.bufferData(g.ARRAY_BUFFER, buf, g.DYNAMIC_DRAW)
        g.bindBuffer(g.ARRAY_BUFFER, null)
      } else {
        console.warn('[V8] GL context or VBO missing; snapshot parsed but not uploaded to GPU.')
      }

      // Commit "last known good" data only AFTER success
      bufferDataRef.current = buf
      v8TypedArraysRef.current = parsed
      pointsDataRef.current = pts
      vertexCountRef.current = parsed.count

      // HUD stats (V8)
      quantumStatsRef.current.assetCount = parsed.count
      quantumStatsRef.current.stride = VERTEX28_STRIDE
      quantumStatsRef.current.snapshotBytes = buf.byteLength
      quantumStatsRef.current.decompressMs = decompressMs
      quantumStatsRef.current.deltaQueueDepth = deltaQueueRef.current.length
      quantumStatsRef.current.fps = fpsRef.current.fps

      setStats(prev => ({
        ...prev,
        points: parsed.count,
        bytes: buf.byteLength,
        stride: VERTEX28_STRIDE,
        noData: false,
        fetchMs: Math.round(performance.now() - fetchStart),
        shaderLog: null
      }))

      return true
    } catch (err: any) {
      if (err?.name === 'AbortError') return false

      const msg = err instanceof Error ? err.message : String(err)
      console.error('[V8] fetchV8Snapshot failed:', err)

      // Preserve last good VBO and typed arrays; only surface the error
      setStats(prev => ({ ...prev, shaderLog: `[V8] snapshot error: ${msg}` }))

      return false
    }
  }

  // Route A: legacy fetchPoints removed

  const fetchSymbols = async (url: string, signal?: AbortSignal): Promise<any[]> => {
    try {
      const resp = await fetch(url, { signal })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      return data.symbols || []
    } catch (err: any) {
      if (err?.name === 'AbortError') return []
      console.error('fetchSymbols failed:', err)
      return []
    }
  }

  useEffect(() => {
    if (picking.hoveredPoint) {
      onHover?.(picking.hoveredPoint)
    } else {
      onHover?.(null)
    }
  }, [picking.hoveredPoint, onHover])

  useEffect(() => {
    if (picking.selectedPoint) {
      const point = picking.selectedPoint
      onSelect?.(point)
      onPick?.(point)
      console.debug('[TitanCanvas] onPick fired', point)
      
      if (onAssetClick) {
        // Extract symbol from point data (prefer point.symbol, fallback to index lookup)
        const pointIndex = point.index ?? (point as any).id ?? 0
        const symbol = point.symbol ?? symbolsMapRef.current?.get(pointIndex) ?? `AST${String(pointIndex).padStart(6, '0')}`
        console.debug('[TitanCanvas] picked symbol=', symbol, 'id=', pointIndex)
        if (symbol && symbol.length > 0) {
          onAssetClick(symbol)
        } else {
          console.warn('[TitanCanvas] onAssetClick skipped: empty symbol', { pointIndex, point })
        }
      }
    }
  }, [picking.selectedPoint, onSelect, onPick, onAssetClick])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    let gl: WebGL2RenderingContext | null = null
    try {
      const ctx = canvas.getContext('webgl2', {
        antialias: false,
        alpha: false,
        depth: false,
        preserveDrawingBuffer: false
      })
      assertWebGL2(ctx)
      gl = ctx
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err)
      setStats(prev => ({ ...prev, shaderLog: `WebGL2 not available: ${errMsg}` }))
      return
    }

    glRef.current = gl

    setCommonGLState(gl)

    let program: WebGLProgram
    try {
      const vs = TITAN_V8_VERTEX_SHADER
      const fs = TITAN_V8_FRAGMENT_SHADER
      program = link(gl, vs, fs)
      programRef.current = program
      programLinkOkRef.current = true
      setStats(prev => ({ ...prev, programLink: true }))
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err)
      shaderLogRef.current = errMsg
      setStats(prev => ({ ...prev, shaderLog: errMsg, programLink: false }))
      return
    }

    if (!useV8Ref.current) {
      let debugProgram: WebGLProgram
      try {
        debugProgram = link(gl, DEBUG_VERTEX_SHADER, TITAN_V8_FRAGMENT_SHADER)
        debugProgramRef.current = debugProgram
        debugProgramLinkOkRef.current = true
        setStats(prev => ({ ...prev, debugProgramLink: true }))
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : String(err)
        shaderLogRef.current = errMsg
        setStats(prev => ({ ...prev, shaderLog: errMsg, debugProgramLink: false }))
      }
    } else {
      debugProgramRef.current = null
      debugProgramLinkOkRef.current = false
      setStats(prev => ({ ...prev, debugProgramLink: false }))
    }

    if (enableSingularityRef.current) {
      try {
        const singularityProgram = link(gl, TITAN_V8_VERTEX_SHADER, SINGULARITY_FRAGMENT_SHADER)
        singularityProgramRef.current = singularityProgram
        console.debug("Shader Singularity program compiled")
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : String(err)
        console.debug(`Shader Singularity compilation failed: ${errMsg}`)
      }
    }

    const vbo = gl.createBuffer()
    if (!vbo) {
      setStats(prev => ({ ...prev, shaderLog: "Failed to create VBO" }))
      return
    }
    bufferRef.current = vbo

    const vao = gl.createVertexArray()
    if (!vao) {
      setStats(prev => ({ ...prev, shaderLog: "Failed to create VAO" }))
      return
    }

    gl.bindVertexArray(vao)
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo)

    // Fetch all attribute locations immediately after program linking
    // V8 mode attributes (Route A)
    const aPosLoc = gl.getAttribLocation(program, 'a_position')
    const aRiskLoc = gl.getAttribLocation(program, 'a_risk')
    const aShockLoc = gl.getAttribLocation(program, 'a_shock')
    const aMortonLoc = gl.getAttribLocation(program, 'a_morton')
    const aMetaLoc = gl.getAttribLocation(program, 'a_meta')
    
    if (aPosLoc < 0) {
      throw new Error("V8 shader missing required attrib a_position")
    }

    // Route A: Vertex28 format attributes
    gl.enableVertexAttribArray(aPosLoc)
    gl.vertexAttribPointer(aPosLoc, 3, gl.FLOAT, false, VERTEX28_STRIDE, V28_OFF_X)
    if (aRiskLoc >= 0) {
      gl.enableVertexAttribArray(aRiskLoc)
      gl.vertexAttribPointer(aRiskLoc, 1, gl.FLOAT, false, VERTEX28_STRIDE, V28_OFF_RISK)
    }
    if (aShockLoc >= 0) {
      gl.enableVertexAttribArray(aShockLoc)
      gl.vertexAttribPointer(aShockLoc, 1, gl.FLOAT, false, VERTEX28_STRIDE, V28_OFF_SHOCK)
    }
    if (aMortonLoc >= 0) {
      gl.enableVertexAttribArray(aMortonLoc)
      gl.vertexAttribIPointer(aMortonLoc, 1, gl.UNSIGNED_INT, VERTEX28_STRIDE, V28_OFF_MORTON)
    }
    if (aMetaLoc >= 0) {
      gl.enableVertexAttribArray(aMetaLoc)
      gl.vertexAttribIPointer(aMetaLoc, 1, gl.UNSIGNED_INT, VERTEX28_STRIDE, V28_OFF_META)
    }

    gl.bindVertexArray(null)
    gl.bindBuffer(gl.ARRAY_BUFFER, null)

    vaoRef.current = vao
    vaoBoundRef.current = true
    setStats(prev => ({ ...prev, vaoBound: true }))

    const resizeCanvas = () => {
      const rect = canvas.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1
      const w = Math.max(2, Math.floor(rect.width * dpr))
      const h = Math.max(2, Math.floor(rect.height * dpr))
      
      canvasWidthRef.current = w
      canvasHeightRef.current = h
      dprRef.current = dpr
      
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w
        canvas.height = h
      }
    }

    resizeCanvas()
    const resizeObserver = new ResizeObserver(resizeCanvas)
    resizeObserver.observe(canvas.parentElement || canvas)

    const worker = createPickingWorker()
    pickingWorkerRef.current = worker
    onAssetClickRef.current = onAssetClick
    if (worker) {
      worker.onmessage = (e) => {
        if (e.data.type === 'built') {
          console.debug('[worker<-msg] type=built')
        } else if (e.data.type === 'result' && e.data.index >= 0) {
          const pointIndex = e.data.index
          const symbol = symbolsMapRef.current?.get(pointIndex) ?? `AST${String(pointIndex).padStart(6, '0')}`
          console.debug('[TitanClick] worker result', { pointIndex, symbol, hasCallback: !!onAssetClickRef.current })
          if (onAssetClickRef.current) {
            onAssetClickRef.current(symbol)
          }
        }
      }
      worker.onerror = (err) => {
        console.warn('Picking worker error:', err)
      }
    }

    const handleKeyPress = (e: KeyboardEvent) => {
      if (e.key === '0') {
        modeRef.current = 0
        setStats(prev => ({ ...prev, mode: 0 }))
      } else if (e.key === '1') {
        modeRef.current = 1
        setStats(prev => ({ ...prev, mode: 1 }))
      } else if (e.key === '2') {
        modeRef.current = 2
        setStats(prev => ({ ...prev, mode: 2 }))
      } else if (e.key === 'd' || e.key === 'D') {
        debugForceRef.current = !debugForceRef.current
        setStats(prev => ({ ...prev, debugForce: debugForceRef.current }))
      } else if (e.key === 'r' || e.key === 'R') {
        camera.reset()
      } else if (e.key === 'f' || e.key === 'F') {
        if (picking.selectedPoint) {
          const worldX = picking.selectedPoint.x01 * 2.0 - 1.0
          const worldY = picking.selectedPoint.y01 * 2.0 - 1.0
          camera.focus(worldX, worldY, 2.0)
        }
      }
    }
    window.addEventListener('keydown', handleKeyPress)

    const render = () => {
      const frameStart = performance.now()
      const g = glRef.current
      if (!g) {
        renderLoopRef.current = requestAnimationFrame(render)
        return
      }

      const now = frameStart
      if (fpsRef.current.lastTime === 0) {
        fpsRef.current.lastTime = now
      }
      fpsRef.current.frames++
      if (now - fpsRef.current.lastTime >= 1000) {
        fpsRef.current.fps = fpsRef.current.frames
        fpsRef.current.frames = 0
        fpsRef.current.lastTime = now
      }

      resizeCanvas()

      const viewportW = g.drawingBufferWidth
      const viewportH = g.drawingBufferHeight
      viewportWidthRef.current = viewportW
      viewportHeightRef.current = viewportH

      g.viewport(0, 0, viewportW, viewportH)
      g.clearColor(0, 0, 0, 1)
      g.clear(g.COLOR_BUFFER_BIT)

      setCommonGLState(g)

      if (debugForceRef.current) {
        const debugProg = debugProgramRef.current
        if (debugProg) {
          g.useProgram(debugProg)
          g.bindVertexArray(null)
          g.drawArrays(g.POINTS, 0, 3)
          drawnCountRef.current = 3
        }
      } else {
        const prog = programRef.current
        const vao = vaoRef.current
        if (!prog || !vao) {
          renderLoopRef.current = requestAnimationFrame(render)
          return
        }

        g.useProgram(prog)
        g.bindVertexArray(vao)

        const uPointSizeLoc = g.getUniformLocation(prog, 'u_pointSize') || g.getUniformLocation(prog, 'u_PointSize') || g.getUniformLocation(prog, 'u_point_size')
        const uTimeLoc = g.getUniformLocation(prog, 'u_time')
        const uModeLoc = g.getUniformLocation(prog, 'u_mode')
        const uZoomLoc = g.getUniformLocation(prog, 'u_zoom')
        const uPanLoc = g.getUniformLocation(prog, 'u_pan')
        const uXyMinLoc = g.getUniformLocation(prog, 'u_xyMin') || g.getUniformLocation(prog, 'u_xy_min')
        const uXyMaxLoc = g.getUniformLocation(prog, 'u_xyMax') || g.getUniformLocation(prog, 'u_xy_max')
        const uRiskMinLoc = g.getUniformLocation(prog, 'u_riskMin')
        const uShockMinLoc = g.getUniformLocation(prog, 'u_shockMin')
        const uTrendMaskLoc = g.getUniformLocation(prog, 'u_trendMask')
        const uGlobalShockFactorLoc = g.getUniformLocation(prog, 'u_GlobalShockFactor') || g.getUniformLocation(prog, 'u_globalShockFactor') || g.getUniformLocation(prog, 'u_global_shock_factor')

        if (uPointSizeLoc) g.uniform1f(uPointSizeLoc, pointSizeRef.current)
        if (uTimeLoc) {
          timeRef.current = performance.now() * 0.001
          g.uniform1f(uTimeLoc, timeRef.current)
        }
        if (uModeLoc) g.uniform1i(uModeLoc, modeRef.current)
        if (uZoomLoc) g.uniform1f(uZoomLoc, camera.camera.zoom)
        if (uPanLoc) g.uniform2f(uPanLoc, camera.camera.panX, camera.camera.panY)
        if (uXyMinLoc) {
          const bounds = boundsRef.current
          g.uniform2f(uXyMinLoc, bounds.minX, bounds.minY)
        }
        if (uXyMaxLoc) {
          const bounds = boundsRef.current
          g.uniform2f(uXyMaxLoc, bounds.maxX, bounds.maxY)
        }
        if (uRiskMinLoc) g.uniform1f(uRiskMinLoc, riskMin)
        if (uShockMinLoc) g.uniform1f(uShockMinLoc, shockMin)
        if (uTrendMaskLoc) {
          let mask = 0
          trendFilter.forEach((t) => {
            if (typeof t === 'number' && t >= 0 && t < 31) mask |= (1 << t)
          })
          if (mask === 0) mask = -1 // allow-all fallback
          g.uniform1i(uTrendMaskLoc, mask)
        }
        if (uGlobalShockFactorLoc) {
          g.uniform1f(uGlobalShockFactorLoc, globalShockFactorRef.current)
        }

        const stride = VERTEX28_STRIDE
        const bufBytes = bufferDataRef.current?.byteLength ?? 0
        const maxCount = bufBytes > 0 ? Math.floor(bufBytes / stride) : vertexCountRef.current
        let drawCount = vertexCountRef.current
        if (drawCount > maxCount) {
          console.warn('[draw] clamping drawCount to buffer capacity', {
            mode: 'v8',
            drawCount,
            maxCount,
            bufBytes,
            stride
          })
          drawCount = maxCount
          vertexCountRef.current = maxCount
        }
        if (drawCount > 0) {
          g.drawArrays(g.POINTS, 0, drawCount)
          drawnCountRef.current = drawCount
        } else {
          drawnCountRef.current = 0
        }

        g.bindVertexArray(null)
      }

      const err = g.getError()
      lastGLErrorRef.current = err
      const errNames: Record<number, string> = {
        [g.NO_ERROR]: 'NO_ERROR',
        [g.INVALID_ENUM]: 'INVALID_ENUM',
        [g.INVALID_VALUE]: 'INVALID_VALUE',
        [g.INVALID_OPERATION]: 'INVALID_OPERATION',
        [g.INVALID_FRAMEBUFFER_OPERATION]: 'INVALID_FRAMEBUFFER',
        [g.OUT_OF_MEMORY]: 'OUT_OF_MEMORY',
        [g.CONTEXT_LOST_WEBGL]: 'CONTEXT_LOST'
      }
      lastGLErrorNameRef.current = errNames[err] || `0x${err.toString(16)}`

      const frameTime = performance.now() - frameStart
      frameTimeRef.current = frameTime

      setStats(prev => ({
        ...prev,
        canvasW: canvasWidthRef.current,
        canvasH: canvasHeightRef.current,
        canvasClientW: canvas.clientWidth,
        canvasClientH: canvas.clientHeight,
        dpr: dprRef.current,
        viewportW: viewportWidthRef.current,
        viewportH: viewportHeightRef.current,
        drawn: drawnCountRef.current,
        glError: err,
        glErrorName: lastGLErrorNameRef.current,
        fps: fpsRef.current.fps,
        frameTime: Math.round(frameTime * 100) / 100
      }))

      renderLoopRef.current = requestAnimationFrame(render)
    }

    renderLoopRef.current = requestAnimationFrame(render)

    return () => {
      clearPollTimer()
      abortRef.current?.abort()
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
  }, [onAssetClick])

  // --- DEFINITIVE POLLING: 5/10s, no overlap, no early start ---
  useEffect(() => {

    const currentEpoch = ++pollEpochRef.current
    const effectivePollMs = Math.max(2000, pollMs ?? 2000)
    let disposed = false

    // Arming delay: first poll cannot happen earlier than effectivePollMs from NOW
    const armAt = Date.now() + effectivePollMs

    const symbolsUrl = null

    const clearTimer = () => {
      if (pollTimerRef.current != null) {
        window.clearTimeout(pollTimerRef.current)
        pollTimerRef.current = null
      }
    }

    const scheduleNext = () => {
      if (disposed || currentEpoch !== pollEpochRef.current) return

      const now = Date.now()
      // Base time: either last actual poll start, or the arming window baseline
      const base = Math.max(lastStartMsRef.current, armAt - effectivePollMs)
      const elapsed = now - base
      const delay = Math.max(0, effectivePollMs - elapsed)

      clearTimer()
      pollTimerRef.current = window.setTimeout(() => {
        void pollOnce()
      }, delay) as any
    }

    const pollOnce = async () => {
      if (disposed || currentEpoch !== pollEpochRef.current) return
      if (inFlightRef.current) return

      const now = Date.now()

      // Safety gate: prevent early starts (including remount edge cases)
      // If lastStartMsRef is 0, we still respect the arming window via scheduleNext()
      if (lastStartMsRef.current !== 0) {
        const sinceLastStart = now - lastStartMsRef.current
        if (sinceLastStart < effectivePollMs) {
          scheduleNext()
          return
        }
      } else {
        // Not yet armed with a previous start time; just reschedule respecting armAt
        scheduleNext()
        return
      }

      // Abort any previous in-flight request
      abortRef.current?.abort()
      const ac = new AbortController()
      abortRef.current = ac

      inFlightRef.current = true
      lastStartMsRef.current = now

      try {
        const ok = await fetchV8Snapshot(ac.signal)
        if (ok && symbolsUrl && !symbolsLoadedRef.current) {
          const symbols = await fetchSymbols(symbolsUrl, ac.signal)
          const symbolStrings = symbols.map((item: any) => item.symbol || `ASSET-${item.id}`)
          symbolsMapRef.current = new Map(symbolStrings.map((s: string, i: number) => [i, s]))
          symbolsLoadedRef.current = true
        }
      } catch (e: any) {
        if (e?.name !== 'AbortError') console.error('[TitanPoll] failed', e)
      } finally {
        inFlightRef.current = false
        if (!disposed && currentEpoch === pollEpochRef.current) scheduleNext()
      }
    }

    // Reset per epoch
    symbolsLoadedRef.current = false

    // expose pollOnce for manual refresh
    pollOnceRef.current = pollOnce

    // SAFE START: do NOT call pollOnce immediately.
    // Set lastStartMsRef such that the earliest allowed poll is at armAt.
    lastStartMsRef.current = armAt - effectivePollMs // baseline for schedule math
    scheduleNext()

    return () => {
      disposed = true
      clearTimer()
      abortRef.current?.abort()
      abortRef.current = null
      inFlightRef.current = false
      lastStartMsRef.current = 0 // CRITICAL reset to avoid timing inheritance
    }
  }, [pollMs])

  // V8: WebSocket delta stream (10Hz)
  useEffect(() => {
    if (!useV8Ref.current) return
    
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsUrl = `${proto}://${window.location.host}/api/universe/v8/stream`
    
    let ws: WebSocket | null = null
    
    const connect = () => {
      try {
        // #region agent log
        fetch('http://127.0.0.1:7242/ingest/2c312865-94f7-427e-905b-dc7584b4541a', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sessionId: 'debug-session',
            runId: 'run1',
            hypothesisId: 'H4',
            location: 'frontend/src/components/TitanCanvas.tsx:ws',
            message: 'ws_connect_attempt',
            data: { wsUrl },
            timestamp: Date.now()
          })
        }).catch(() => {})
        // #endregion agent log
        ws = new WebSocket(wsUrl)
        ws.binaryType = 'arraybuffer'
        
        ws.onopen = () => {
          console.log('[V8] WebSocket connected')
          quantumStatsRef.current.lastWSLagMs = 0
          // #region agent log
          fetch('http://127.0.0.1:7242/ingest/2c312865-94f7-427e-905b-dc7584b4541a', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              sessionId: 'debug-session',
              runId: 'run1',
              hypothesisId: 'H4',
              location: 'frontend/src/components/TitanCanvas.tsx:ws',
              message: 'ws_open',
              data: { wsUrl },
              timestamp: Date.now()
            })
          }).catch(() => {})
          // #endregion agent log
        }
        
        ws.onmessage = async (event) => {
          const receiveStart = performance.now()
          try {
            // Route A (minimal stream): JSON heartbeat/keepalive.
            if (typeof event.data === 'string') {
              // keepalive only
              quantumStatsRef.current.lastWSLagMs = Math.round(performance.now() - receiveStart)
              return
            }
            // Ignore binary until delta protocol is implemented.
            quantumStatsRef.current.lastWSLagMs = Math.round(performance.now() - receiveStart)
          } catch (e) {
            console.error('[V8] WebSocket message processing failed:', e)
          }
        }
        
        ws.onerror = (err) => {
          console.error('[V8] WebSocket error:', err)
          // #region agent log
          fetch('http://127.0.0.1:7242/ingest/2c312865-94f7-427e-905b-dc7584b4541a', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              sessionId: 'debug-session',
              runId: 'run1',
              hypothesisId: 'H4',
              location: 'frontend/src/components/TitanCanvas.tsx:ws',
              message: 'ws_error',
              data: { wsUrl },
              timestamp: Date.now()
            })
          }).catch(() => {})
          // #endregion agent log
        }
        
        ws.onclose = () => {
          console.log('[V8] WebSocket closed')
          // #region agent log
          fetch('http://127.0.0.1:7242/ingest/2c312865-94f7-427e-905b-dc7584b4541a', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              sessionId: 'debug-session',
              runId: 'run1',
              hypothesisId: 'H4',
              location: 'frontend/src/components/TitanCanvas.tsx:ws',
              message: 'ws_close',
              data: { wsUrl },
              timestamp: Date.now()
            })
          }).catch(() => {})
          // #endregion agent log
        }
        
        wsRef.current = ws
      } catch (e) {
        console.error('[V8] WebSocket connection failed:', e)
      }
    }
    
    connect()
    
    return () => {
      if (ws) {
        ws.close()
        wsRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    pointSizeRef.current = Math.max(2.0, pointSize)
  }, [pointSize])

  useEffect(() => {
    onAssetClickRef.current = onAssetClick
  }, [onAssetClick])

  useEffect(() => {
    if (!pointsData.length || !pickingWorkerRef.current) return

    const pointsHash = pointsData.length
    const cameraHash = Math.floor(camera.camera.zoom * 1000) ^ Math.floor(camera.camera.panX * 1000) ^ Math.floor(camera.camera.panY * 1000)
    
    if (lastGridBuildRef.current?.pointsHash === pointsHash && lastGridBuildRef.current?.cameraHash === cameraHash) {
      return
    }

    const canvas = canvasRef.current
    if (!canvas) return

    const rect = canvas.getBoundingClientRect()
    const positions = new Float32Array(pointsData.length * 2)
    
    for (let i = 0; i < pointsData.length; i++) {
      const p = pointsData[i]
      const worldX = p.x01 * 2.0 - 1.0
      const worldY = p.y01 * 2.0 - 1.0
      const camX = (worldX + camera.camera.panX) * camera.camera.zoom
      const camY = (worldY + camera.camera.panY) * camera.camera.zoom
      const screenX = (camX * 0.5 + 0.5) * rect.width
      const screenY = (camY * -0.5 + 0.5) * rect.height
      positions[i * 2] = screenX
      positions[i * 2 + 1] = screenY
    }

    screenPositionsRef.current = positions
    // Log when positions are set (triggers hasPositions change)
    if (lastHasPositionsRef.current !== true) {
      console.debug('[points] hasPositions changed to true')
      lastHasPositionsRef.current = true
    }

    if (pickingWorkerRef.current) {
      console.debug('[worker->post] positionsLen=', positions.length, 'count=', pointsData.length)
      pickingWorkerRef.current.postMessage({
        type: 'build',
        data: {
          positions,
          width: rect.width,
          height: rect.height
        }
      }, [positions.buffer])
      
      lastGridBuildRef.current = { pointsHash, cameraHash }
    }
  }, [pointsData, camera.camera.panX, camera.camera.panY, camera.camera.zoom])

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    mousePosRef.current = { x: e.clientX, y: e.clientY }
    picking.handleMouseMove(e)
    camera.handleMouseMove(e)
  }, [picking, camera])

  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button === 0) {
      const canvas = canvasRef.current
      const worker = pickingWorkerRef.current
      console.debug('[TitanClick] handleMouseDown', { hasCanvas: !!canvas, hasWorker: !!worker, hasPositions: !!screenPositionsRef.current, pointsCount: pointsData.length })
      
      // Try worker path first (if available)
      if (canvas && worker && screenPositionsRef.current && screenPositionsRef.current.length > 0) {
        const rect = canvas.getBoundingClientRect()
        const clickX = e.clientX - rect.left
        const clickY = e.clientY - rect.top
        
        console.debug('[TitanClick] sending worker query', { clickX, clickY })
        worker.postMessage({
          type: 'query',
          data: { x: clickX, y: clickY, radiusPx: 12 }
        })
        // Don't return - also try picking fallback in case worker fails
      }
      
      // Fallback: use picking hook (works even if worker unavailable)
      console.debug('[TitanClick] also trying picking.handleClick')
      picking.handleClick(e)
    }
    camera.handleMouseDown(e)
  }, [picking, camera, onAssetClick, pointsData.length])

  const handleMouseUp = useCallback(() => {
    camera.handleMouseUp()
  }, [camera])

  const handleWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    camera.handleWheel(e)
  }, [camera])

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <canvas
        ref={canvasRef}
        width={1920}
        height={1080}
        style={{ width: '100%', height: '100%', display: 'block', zIndex: 1, cursor: picking.hoveredPoint ? 'pointer' : 'default' }}
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onWheel={handleWheel}
      />
      {picking.hoveredPoint && (
        <PointTooltip point={picking.hoveredPoint} mousePos={mousePosRef.current} />
      )}
      {stats.noData && (
        <div style={{
          position: 'absolute',
          top: '1rem',
          left: '1rem',
          background: 'rgba(255, 193, 7, 0.9)',
          color: 'black',
          padding: '0.5rem 1rem',
          borderRadius: '4px',
          fontSize: '0.875rem',
          fontWeight: 'bold',
          zIndex: 100
        }}>
          UNIVERSE: NO DATA (204)
        </div>
      )}
      {stats.shaderLog && (
        <div style={{
          position: 'absolute',
          top: stats.noData ? '3.5rem' : '1rem',
          left: '1rem',
          background: 'rgba(255, 0, 0, 0.8)',
          color: 'white',
          padding: '0.5rem',
          fontFamily: 'monospace',
          fontSize: '0.75rem',
          zIndex: 1000
        }}>
          {stats.shaderLog}
        </div>
      )}
      {/* Quantum Stats HUD (V8) */}
      {useV8Ref.current && (
        <div style={{
          position: 'absolute',
          bottom: '1rem',
          right: '1rem',
          background: 'rgba(0, 0, 0, 0.8)',
          color: '#00ff00',
          padding: '0.75rem',
          fontFamily: 'monospace',
          fontSize: '0.75rem',
          borderRadius: '4px',
          zIndex: 1000,
          minWidth: '200px'
        }}>
          <div style={{ fontWeight: 'bold', marginBottom: '0.5rem', color: '#ffaa00' }}>QUANTUM STATS</div>
          <div>Assets: {quantumStatsRef.current.assetCount.toLocaleString()}</div>
          <div>Stride: {quantumStatsRef.current.stride}B</div>
          <div>Snapshot: {(quantumStatsRef.current.snapshotBytes / 1024).toFixed(1)}KB</div>
          <div>Decompress: {quantumStatsRef.current.decompressMs}ms</div>
          <div>Parse: {quantumStatsRef.current.parseMs}ms</div>
          <div>FPS: {quantumStatsRef.current.fps}</div>
          <div>Delta Queue: {quantumStatsRef.current.deltaQueueDepth}</div>
          <div>WS Lag: {quantumStatsRef.current.lastWSLagMs}ms</div>
        </div>
      )}
    </div>
  )
})

TitanCanvas.displayName = 'TitanCanvas'
