import { useEffect, useRef, useState, useImperativeHandle, forwardRef, useCallback, useMemo } from 'react'
import { useCamera, type CameraState } from '../hooks/useCamera'
import { usePointPicking, type PointData } from '../hooks/usePointPicking'
import { usePointData } from '../hooks/usePointData'
import { PointTooltip } from './PointTooltip'
import { AssetDetailPanel } from './AssetDetailPanel'
import { TITAN_V8_VERTEX_SHADER, TITAN_V8_FRAGMENT_SHADER, PICKING_VERTEX_SHADER, PICKING_FRAGMENT_SHADER } from '../render/quantumShaders'

export interface TitanCanvasRef {
  refresh: () => void
  focusPoint: (point: PointData) => void
}

interface TitanCanvasProps {
  pointSize?: number
  glowStrength?: number
  streamUrlBin?: string
  streamUrlMeta?: string
  streamUrlSymbols?: string
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

const STRIDE_BYTES = 12
const VERTEX28_STRIDE = 28
const OFF_X = 0
const OFF_Y = 2
const OFF_ATTR = 4
const OFF_META = 8

// Vertex28 offsets
const V28_OFF_TAXONOMY = 0
const V28_OFF_META = 4
const V28_OFF_X = 8
const V28_OFF_Y = 12
const V28_OFF_Z = 16
const V28_OFF_FIDELITY = 20
const V28_OFF_SPIN = 24

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

const TITAN_VERTEX_SHADER = `#version 300 es
precision highp float;
precision highp int;

layout(location=0) in uint a_x;
layout(location=1) in uint a_y;
layout(location=2) in uint a_attr;
layout(location=3) in uint a_meta;

uniform float u_pointSize;
uniform float u_time;
uniform int u_mode;
uniform float u_zoom;
uniform vec2 u_pan;
uniform vec2 u_xyMin;
uniform vec2 u_xyMax;
uniform float u_riskMin;
uniform float u_shockMin;
uniform int u_trendMask;
uniform float u_GlobalShockFactor;

out vec4 v_color;

uint get_bits(uint x, uint shift, uint mask) {
  return (x >> shift) & mask;
}

void main() {
  uint shock = get_bits(a_meta, 0u, 255u);
  uint risk  = get_bits(a_meta, 8u, 255u);
  uint trend = get_bits(a_meta, 16u, 3u);
  uint vital = get_bits(a_meta, 18u, 63u);
  uint macro = get_bits(a_meta, 24u, 255u);

  float fshock = float(shock) / 255.0;
  float frisk  = float(risk)  / 255.0;
  float fvital = float(vital) / 63.0;
  float fmacro = float(macro) / 255.0;

  float filterAlpha = 1.0;
  if (frisk < u_riskMin) filterAlpha = 0.0;
  if (fshock < u_shockMin) filterAlpha = 0.0;
  if ((u_trendMask & (1 << int(trend))) == 0) filterAlpha = 0.0;

  float xf = float(a_x);
  float yf = float(a_y);

  vec2 denom = max(u_xyMax - u_xyMin, vec2(1.0));
  vec2 p01 = (vec2(xf, yf) - u_xyMin) / denom;
  
  if (denom.x == 1.0 && denom.y == 1.0) {
    float angle = float(gl_VertexID) * 0.618034 * 6.28318;
    float radius = 0.1 + float(gl_VertexID) * 0.0001;
    p01 = vec2(0.5, 0.5) + vec2(cos(angle), sin(angle)) * radius;
  }
  
  vec2 pos = p01 * 2.0 - 1.0;

  if (fshock > 0.05) {
    float w = 18.0 + 24.0 * fshock;
    float amp = 0.002 + 0.010 * fshock;
    pos += vec2(sin(u_time * w), cos(u_time * w)) * amp;
  }

  vec2 cam = (pos + u_pan) * u_zoom;
  gl_Position = vec4(cam, 0.0, 1.0);

  float ps = max(2.0, u_pointSize);

  if (u_mode == 2) {
    vec3 base;
    if (trend == 1u)      base = vec3(0.0, 1.0, 1.0);
    else if (trend == 2u) base = vec3(1.0, 0.0, 1.0);
    else                  base = vec3(0.75);

    float globalPulse = 1.0 + sin(u_time * 3.0) * u_GlobalShockFactor * 0.1;
    float intensity = (0.40 + 1.60 * frisk) * globalPulse;
    intensity *= (0.85 + 0.30 * fmacro);

    float alpha = max(0.08, fvital) * filterAlpha;

    v_color = vec4(base * intensity, alpha);
    gl_PointSize = ps * (1.0 + 2.0 * frisk) * (1.0 + u_GlobalShockFactor * 0.2);
  }
  else if (u_mode == 1) {
    float intensity = 0.25 + 2.25 * frisk;
    v_color = vec4(vec3(intensity), 0.85 * filterAlpha);
    gl_PointSize = ps * (1.0 + 1.5 * frisk);
  }
  else {
    v_color = vec4(1.0, 1.0, 1.0, 0.8 * filterAlpha);
    gl_PointSize = ps;
  }
}
`

const TITAN_FRAGMENT_SHADER = `#version 300 es
precision highp float;

in vec4 v_color;
out vec4 outColor;

void main() {
  vec2 uv = gl_PointCoord * 2.0 - 1.0;
  float r2 = dot(uv, uv);
  if (r2 > 1.0) discard;

  float a = v_color.a * smoothstep(1.0, 0.0, r2);
  outColor = vec4(v_color.rgb, a);
}
`

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
  gl.disable(gl.DEPTH_TEST)
  gl.disable(gl.CULL_FACE)
}

interface Bounds {
  minX: number
  maxX: number
  minY: number
  maxY: number
  uniqueX: number
  uniqueY: number
  degenerate: boolean
}

function computeBounds(ab: ArrayBuffer, count: number): Bounds {
  const view = new DataView(ab)
  const xSet = new Set<number>()
  const ySet = new Set<number>()
  let minX = 65535, maxX = 0, minY = 65535, maxY = 0

  for (let i = 0; i < count; i++) {
    const off = i * STRIDE_BYTES
    const x = view.getUint16(off + OFF_X, true)
    const y = view.getUint16(off + OFF_Y, true)
    xSet.add(x)
    ySet.add(y)
    if (x < minX) minX = x
    if (x > maxX) maxX = x
    if (y < minY) minY = y
    if (y > maxY) maxY = y
  }

  return {
    minX,
    maxX,
    minY,
    maxY,
    uniqueX: xSet.size,
    uniqueY: ySet.size,
    degenerate: (minX === maxX) || (minY === maxY)
  }
}

async function decodePoints(ab: ArrayBuffer, symbolsMap: Map<number, string>, bounds: Bounds): Promise<PointData[]> {
  const view = new DataView(ab)
  const count = Math.floor(ab.byteLength / STRIDE_BYTES)
  const decoded: PointData[] = []

  for (let i = 0; i < count; i++) {
    const off = i * STRIDE_BYTES
    const x = view.getUint16(off + OFF_X, true)
    const y = view.getUint16(off + OFF_Y, true)
    const meta32 = view.getUint32(off + OFF_META, true)

    const shock8 = meta32 & 0xFF
    const risk8 = (meta32 >> 8) & 0xFF
    const trend2 = (meta32 >> 16) & 0x03
    const vital6 = (meta32 >> 18) & 0x3F
    const macro8 = (meta32 >> 24) & 0xFF

    const denomX = bounds.maxX - bounds.minX || 1
    const denomY = bounds.maxY - bounds.minY || 1

    decoded.push({
      index: i,
      x01: (x - bounds.minX) / denomX,
      y01: (y - bounds.minY) / denomY,
      shock: shock8 / 255.0,
      risk: risk8 / 255.0,
      trend: trend2,
      vital: vital6 / 63.0,
      macro: macro8 / 255.0,
      symbol: symbolsMap.get(i) || `AST${String(i).padStart(6, '0')}`,
      assetId: i
    })
  }

  return decoded
}

export const TitanCanvas = forwardRef<TitanCanvasRef, TitanCanvasProps>(({
  pointSize = 10.0,
  glowStrength = 1.0,
  streamUrlBin = '/api/universe/points.bin?limit=10000',
  streamUrlMeta = '/api/universe/points.meta?limit=10000',
  streamUrlSymbols = '/api/universe/points.symbols?limit=10000',
  pollMs = 500,
  riskMin = 0,
  shockMin = 0,
  trendFilter = new Set([0, 1, 2]),
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
  const useV8Ref = useRef(true) // Toggle for V8 vs legacy
  const v8BackoffUntilRef = useRef(0) // Timestamp until which V8 is disabled due to 503
  const v8NextRetryAtRef = useRef<number>(0)
  const v8TypedArraysRef = useRef<{
    positions: Float32Array | null
    fidelity: Float32Array | null
    taxonomy: Uint32Array | null
    meta: Uint32Array | null
    spin: Float32Array | null
    count: number
  }>({
    positions: null,
    fidelity: null,
    taxonomy: null,
    meta: null,
    spin: null,
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

  const processPointsData = async (ab: ArrayBuffer) => {
    if (ab.byteLength === 0) return
    if (ab.byteLength % 12 !== 0) return
    
    const fetchStart = performance.now()
    const count = Math.floor(ab.byteLength / 12)
    vertexCountRef.current = count
    bufferDataRef.current = ab
    
    const bounds = computeBounds(ab, count)
    boundsRef.current = bounds
    
    const symbolsMap = symbolsMapRef.current || new Map()
    const decoded = await decodePoints(ab, symbolsMap, bounds)
    pointsDataRef.current = decoded
    
    const sampleSize = Math.min(256, decoded.length)
    let shockSum = 0.0
    for (let i = 0; i < sampleSize; i++) {
      shockSum += decoded[i].shock
    }
    globalShockFactorRef.current = sampleSize > 0 ? shockSum / sampleSize : 0.0
    
    const fetchMs = Math.round((performance.now() - fetchStart))
    
    setStats(prev => ({
      ...prev,
      points: count,
      bytes: ab.byteLength,
      stride: 12,
      fetchMs,
      xMin: bounds.minX,
      xMax: bounds.maxX,
      yMin: bounds.minY,
      yMax: bounds.maxY,
      xyDegen: bounds.degenerate,
      uniqueX512: bounds.uniqueX,
      uniqueY512: bounds.uniqueY,
      dataDegenerateFallback: bounds.degenerate
    }))
    
    const gl = glRef.current
    const vbo = bufferRef.current
    if (gl && vbo && count > 0) {
      gl.bindBuffer(gl.ARRAY_BUFFER, vbo)
      const u8 = new Uint8Array(ab)
      gl.bufferData(gl.ARRAY_BUFFER, u8, gl.DYNAMIC_DRAW)
      const err = gl.getError()
      if (err !== gl.NO_ERROR) {
        console.warn('[legacy] gl.bufferData error', { err, bytes: ab.byteLength, count })
        debugForceRef.current = true
        setStats(prev => ({ ...prev, shaderLog: 'WebGL upload failed in legacy mode; forcing debug renderer.' }))
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, null)
    }
  }

  const rebuildPipelineIfNeeded = useCallback((wantV8: boolean) => {
    if (useV8Ref.current === wantV8) return
    const gl = glRef.current
    const vbo = bufferRef.current
    if (!gl || !vbo) {
      useV8Ref.current = wantV8
      return
    }

    try {
      useV8Ref.current = wantV8

      const vs = wantV8 ? TITAN_V8_VERTEX_SHADER : TITAN_VERTEX_SHADER
      const fs = wantV8 ? TITAN_V8_FRAGMENT_SHADER : TITAN_FRAGMENT_SHADER
      const prog = link(gl, vs, fs)

      if (programRef.current) gl.deleteProgram(programRef.current)
      programRef.current = prog
      programLinkOkRef.current = true
      setStats(prev => ({ ...prev, programLink: true, shaderLog: null }))

      if (vaoRef.current) gl.deleteVertexArray(vaoRef.current)
      const vao = gl.createVertexArray()
      if (!vao) throw new Error('Failed to create VAO')

      gl.bindVertexArray(vao)
      gl.bindBuffer(gl.ARRAY_BUFFER, vbo)

      // V8 mode attributes
      const aPosLoc = gl.getAttribLocation(prog, 'a_position')
      const aFidelityLoc = gl.getAttribLocation(prog, 'a_fidelity')
      const aTaxonomyLoc = gl.getAttribLocation(prog, 'a_taxonomy')
      const aMetaLoc = gl.getAttribLocation(prog, 'a_meta')
      const aSpinLoc = gl.getAttribLocation(prog, 'a_spin')

      // Legacy mode attributes
      const aXLoc = gl.getAttribLocation(prog, 'a_x')
      const aYLoc = gl.getAttribLocation(prog, 'a_y')
      const aAttrLoc = gl.getAttribLocation(prog, 'a_attr')
      const aMetaLocLegacy = gl.getAttribLocation(prog, 'a_meta')

      if (wantV8) {
        if (aPosLoc >= 0) {
          gl.enableVertexAttribArray(aPosLoc)
          gl.vertexAttribPointer(aPosLoc, 3, gl.FLOAT, false, VERTEX28_STRIDE, V28_OFF_X)
        }
        if (aFidelityLoc >= 0) {
          gl.enableVertexAttribArray(aFidelityLoc)
          gl.vertexAttribPointer(aFidelityLoc, 1, gl.FLOAT, false, VERTEX28_STRIDE, V28_OFF_FIDELITY)
        }
        if (aTaxonomyLoc >= 0) {
          gl.enableVertexAttribArray(aTaxonomyLoc)
          gl.vertexAttribIPointer(aTaxonomyLoc, 1, gl.UNSIGNED_INT, VERTEX28_STRIDE, V28_OFF_TAXONOMY)
        }
        if (aMetaLoc >= 0) {
          gl.enableVertexAttribArray(aMetaLoc)
          gl.vertexAttribIPointer(aMetaLoc, 1, gl.UNSIGNED_INT, VERTEX28_STRIDE, V28_OFF_META)
        }
        if (aSpinLoc >= 0) {
          gl.enableVertexAttribArray(aSpinLoc)
          gl.vertexAttribPointer(aSpinLoc, 1, gl.FLOAT, false, VERTEX28_STRIDE, V28_OFF_SPIN)
        }
      } else {
        if (aXLoc >= 0) {
          gl.enableVertexAttribArray(aXLoc)
          gl.vertexAttribIPointer(aXLoc, 1, gl.UNSIGNED_SHORT, STRIDE_BYTES, OFF_X)
        }
        if (aYLoc >= 0) {
          gl.enableVertexAttribArray(aYLoc)
          gl.vertexAttribIPointer(aYLoc, 1, gl.UNSIGNED_SHORT, STRIDE_BYTES, OFF_Y)
        }
        if (aAttrLoc >= 0) {
          gl.enableVertexAttribArray(aAttrLoc)
          gl.vertexAttribIPointer(aAttrLoc, 1, gl.UNSIGNED_INT, STRIDE_BYTES, OFF_ATTR)
        }
        if (aMetaLocLegacy >= 0) {
          gl.enableVertexAttribArray(aMetaLocLegacy)
          gl.vertexAttribIPointer(aMetaLocLegacy, 1, gl.UNSIGNED_INT, STRIDE_BYTES, OFF_META)
        }
      }

      gl.bindVertexArray(null)
      gl.bindBuffer(gl.ARRAY_BUFFER, null)

      vaoRef.current = vao
      vaoBoundRef.current = true
      setStats(prev => ({ ...prev, vaoBound: true }))
    } catch (e: any) {
      const msg = e instanceof Error ? e.message : String(e)
      console.error('[TitanCanvas] pipeline rebuild failed', { wantV8, msg })
      debugForceRef.current = true
      setStats(prev => ({ ...prev, shaderLog: `Pipeline rebuild failed (${wantV8 ? 'V8' : 'legacy'}): ${msg}` }))
    }
  }, [])

  // V8: Decompress Zstd
  const decompressZstd = async (compressed: ArrayBuffer): Promise<ArrayBuffer> => {
    try {
      // Try zstd-codec first (preferred)
      const { ZstdCodec } = await import('zstd-codec')
      const codec = await ZstdCodec.load()
      const stream = new codec.Stream()
      const decompressed = stream.decompress(new Uint8Array(compressed))
      return decompressed.buffer
    } catch (e) {
      console.warn('[V8] zstd-codec not available, trying fallback:', e)
      // Fallback: if backend didn't compress, return as-is
      return compressed
    }
  }

  // V8: Parse Vertex28 format
  const parseVertex28 = (buffer: ArrayBuffer): {
    positions: Float32Array
    fidelity: Float32Array
    taxonomy: Uint32Array
    meta: Uint32Array
    spin: Float32Array
    count: number
  } => {
    const parseStart = performance.now()
    const bytes = new Uint8Array(buffer)
    const count = Math.floor(bytes.length / VERTEX28_STRIDE)
    
    // Pre-allocate typed arrays (zero-copy strategy)
    const positions = new Float32Array(count * 3)
    const fidelity = new Float32Array(count)
    const taxonomy = new Uint32Array(count)
    const meta = new Uint32Array(count)
    const spin = new Float32Array(count)
    
    // Parse using DataView for exact offset access
    const view = new DataView(buffer)
    for (let i = 0; i < count; i++) {
      const offset = i * VERTEX28_STRIDE
      
      // Extract fields at exact offsets
      taxonomy[i] = view.getUint32(offset + V28_OFF_TAXONOMY, true) // little-endian
      meta[i] = view.getUint32(offset + V28_OFF_META, true)
      positions[i * 3] = view.getFloat32(offset + V28_OFF_X, true)
      positions[i * 3 + 1] = view.getFloat32(offset + V28_OFF_Y, true)
      positions[i * 3 + 2] = view.getFloat32(offset + V28_OFF_Z, true)
      fidelity[i] = view.getFloat32(offset + V28_OFF_FIDELITY, true)
      spin[i] = view.getFloat32(offset + V28_OFF_SPIN, true)
    }
    
    const parseMs = Math.round(performance.now() - parseStart)
    quantumStatsRef.current.parseMs = parseMs
    
    return { positions, fidelity, taxonomy, meta, spin, count }
  }

  // V8: Fetch snapshot
  const fetchV8Snapshot = async (signal?: AbortSignal): Promise<boolean> => {
    try {
      const url = '/api/universe/v8/snapshot?format=vertex28&compression=zstd'
      const fetchStart = performance.now()
      
      const resp = await fetch(url, { signal })
      
      if (resp.status === 204) {
        console.warn('[V8] 204 No Content')
        setStats(prev => ({ ...prev, noData: true }))
        return false
      }
      
      if (resp.status === 503) {
        console.warn('[V8] snapshot 503: backend/proxy unavailable; falling back to legacy')
        setStats(prev => ({ ...prev, shaderLog: 'V8 snapshot unavailable (503). Using legacy mode.' }))
        v8NextRetryAtRef.current = Date.now() + 5000
        return false
      }
      
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      
      // Get headers
      const stride = resp.headers.get('X-Vertex-Stride')
      const assetCount = resp.headers.get('X-Asset-Count')
      const version = resp.headers.get('X-Titan-Version')
      
      if (stride !== '28') {
        console.error('[V8] Invalid stride:', stride)
        return false
      }
      
      const compressed = await resp.arrayBuffer()
      const snapshotBytes = compressed.byteLength
      
      // Decompress
      const decompressStart = performance.now()
      const decompressed = await decompressZstd(compressed)
      const decompressMs = Math.round(performance.now() - decompressStart)

      // Keep latest buffer for drawCount safety checks (and to prevent stride/count mismatches).
      bufferDataRef.current = decompressed
      
      quantumStatsRef.current = {
        assetCount: parseInt(assetCount || '0', 10),
        stride: 28,
        snapshotBytes,
        decompressMs,
        parseMs: 0,
        fps: fpsRef.current.fps,
        deltaQueueDepth: deltaQueueRef.current.length,
        lastWSLagMs: 0
      }
      
      // Parse Vertex28
      const parsed = parseVertex28(decompressed)
      v8TypedArraysRef.current = parsed
      
      // Update WebGL buffers
      const gl = glRef.current
      if (gl && bufferRef.current && parsed.count > 0) {
        gl.bindBuffer(gl.ARRAY_BUFFER, bufferRef.current)
        gl.bufferData(gl.ARRAY_BUFFER, decompressed, gl.DYNAMIC_DRAW)
        const err = gl.getError()
        if (err !== gl.NO_ERROR) {
          console.warn('[V8] gl.bufferData error', { err, bytes: decompressed.byteLength, count: parsed.count })
          debugForceRef.current = true
          setStats(prev => ({ ...prev, shaderLog: 'WebGL upload failed in V8 mode; forcing debug renderer.' }))
        }
        gl.bindBuffer(gl.ARRAY_BUFFER, null)
      }
      
      vertexCountRef.current = parsed.count
      
      setStats(prev => ({
        ...prev,
        points: parsed.count,
        bytes: decompressed.byteLength,
        stride: 28,
        noData: false,
        fetchMs: Math.round(performance.now() - fetchStart)
      }))
      
      return true
    } catch (err: any) {
      if (err?.name === 'AbortError') return false
      console.error('[V8] fetchV8Snapshot failed:', err)
      return false
    }
  }

  const fetchPoints = async (url: string, signal?: AbortSignal): Promise<ArrayBuffer | null> => {
    try {
      // Use relative path - Vite proxy handles routing to backend
      // Dev-only instrumentation logs
      if (import.meta.env.DEV) {
        console.debug('[fetchPoints] url=', url)
      }
      
      const resp = await fetch(url, { signal })
      
      // Handle HTTP 204 No Content explicitly
      if (resp.status === 204) {
        console.warn('[fetchPoints] 204 No Content (no universe data)')
        setStats(prev => ({ ...prev, noData: true }))
        return null // Sentinel: no data available
      }
      
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      
      const ab = await resp.arrayBuffer()
      
      // Dev-only instrumentation: log response details (only for 200 OK)
      if (import.meta.env.DEV && resp.status === 200 && resp.ok) {
        const contentLength = resp.headers.get('content-length')
        console.debug('[fetchPoints] status=200 content-length=', contentLength, 'arrayBuffer=', ab.byteLength)
      }
      
      // Clear noData flag on successful data fetch
      setStats(prev => ({ ...prev, noData: false }))
      
      await processPointsData(ab)
      
      return ab
    } catch (err: any) {
      if (err?.name === 'AbortError') return null
      console.error('fetchPoints failed:', err)
      return null
    }
  }

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
      const vs = useV8Ref.current ? TITAN_V8_VERTEX_SHADER : TITAN_VERTEX_SHADER
      const fs = useV8Ref.current
        ? (typeof TITAN_V8_FRAGMENT_SHADER !== 'undefined' ? TITAN_V8_FRAGMENT_SHADER : TITAN_FRAGMENT_SHADER)
        : TITAN_FRAGMENT_SHADER
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
        debugProgram = link(gl, DEBUG_VERTEX_SHADER, TITAN_FRAGMENT_SHADER)
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
        const singularityProgram = link(gl, TITAN_VERTEX_SHADER, SINGULARITY_FRAGMENT_SHADER)
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
    // V8 mode attributes
    const aPosLoc = gl.getAttribLocation(program, 'a_position')
    const aFidelityLoc = gl.getAttribLocation(program, 'a_fidelity')
    const aTaxonomyLoc = gl.getAttribLocation(program, 'a_taxonomy')
    const aMetaLoc = gl.getAttribLocation(program, 'a_meta')
    const aSpinLoc = gl.getAttribLocation(program, 'a_spin')
    
    // Legacy mode attributes
    const aXLoc = gl.getAttribLocation(program, 'a_x')
    const aYLoc = gl.getAttribLocation(program, 'a_y')
    const aAttrLoc = gl.getAttribLocation(program, 'a_attr')
    const aMetaLocLegacy = gl.getAttribLocation(program, 'a_meta')

    // Validate critical attributes
    if (useV8Ref.current) {
      if (aPosLoc < 0) {
        throw new Error("V8 shader missing required attrib a_position")
      }
      if (aTaxonomyLoc < 0) {
        console.warn("[TitanCanvas] Attribute 'a_taxonomy' not found (may be optimized out)")
      }
      if (aMetaLoc < 0) {
        console.warn("[TitanCanvas] Attribute 'a_meta' not found (may be optimized out)")
      }
    } else {
      if (aXLoc < 0 || aYLoc < 0) {
        const errMsg = "Critical attributes 'a_x' or 'a_y' not found in shader program"
        console.error(`[TitanCanvas] ${errMsg}`)
        setStats(prev => ({ ...prev, shaderLog: errMsg }))
        return
      }
      if (aMetaLocLegacy < 0) {
        console.warn("[TitanCanvas] Attribute 'a_meta' not found (may be optimized out)")
      }
    }

    // Bind attributes based on mode
    if (useV8Ref.current) {
      // V8: Vertex28 format attributes
      if (aPosLoc >= 0) {
        gl.enableVertexAttribArray(aPosLoc)
        gl.vertexAttribPointer(aPosLoc, 3, gl.FLOAT, false, VERTEX28_STRIDE, V28_OFF_X)
      }
      if (aFidelityLoc >= 0) {
        gl.enableVertexAttribArray(aFidelityLoc)
        gl.vertexAttribPointer(aFidelityLoc, 1, gl.FLOAT, false, VERTEX28_STRIDE, V28_OFF_FIDELITY)
      }
      if (aTaxonomyLoc >= 0) {
        gl.enableVertexAttribArray(aTaxonomyLoc)
        gl.vertexAttribIPointer(aTaxonomyLoc, 1, gl.UNSIGNED_INT, VERTEX28_STRIDE, V28_OFF_TAXONOMY)
      }
      if (aMetaLoc >= 0) {
        gl.enableVertexAttribArray(aMetaLoc)
        gl.vertexAttribIPointer(aMetaLoc, 1, gl.UNSIGNED_INT, VERTEX28_STRIDE, V28_OFF_META)
      }
      if (aSpinLoc >= 0) {
        gl.enableVertexAttribArray(aSpinLoc)
        gl.vertexAttribPointer(aSpinLoc, 1, gl.FLOAT, false, VERTEX28_STRIDE, V28_OFF_SPIN)
      }
    } else {
      // Legacy: 12-byte stride attributes
      if (aXLoc >= 0) {
        gl.enableVertexAttribArray(aXLoc)
        gl.vertexAttribIPointer(aXLoc, 1, gl.UNSIGNED_SHORT, STRIDE_BYTES, OFF_X)
      }
      if (aYLoc >= 0) {
        gl.enableVertexAttribArray(aYLoc)
        gl.vertexAttribIPointer(aYLoc, 1, gl.UNSIGNED_SHORT, STRIDE_BYTES, OFF_Y)
      }
      if (aAttrLoc >= 0) {
        gl.enableVertexAttribArray(aAttrLoc)
        gl.vertexAttribIPointer(aAttrLoc, 1, gl.UNSIGNED_INT, STRIDE_BYTES, OFF_ATTR)
      }
      if (aMetaLocLegacy >= 0) {
        gl.enableVertexAttribArray(aMetaLocLegacy)
        gl.vertexAttribIPointer(aMetaLocLegacy, 1, gl.UNSIGNED_INT, STRIDE_BYTES, OFF_META)
      }
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

        const uPointSizeLoc = g.getUniformLocation(prog, 'u_pointSize')
        const uTimeLoc = g.getUniformLocation(prog, 'u_time')
        const uModeLoc = g.getUniformLocation(prog, 'u_mode')
        const uZoomLoc = g.getUniformLocation(prog, 'u_zoom')
        const uPanLoc = g.getUniformLocation(prog, 'u_pan')
        const uXyMinLoc = g.getUniformLocation(prog, 'u_xyMin')
        const uXyMaxLoc = g.getUniformLocation(prog, 'u_xyMax')
        const uRiskMinLoc = g.getUniformLocation(prog, 'u_riskMin')
        const uShockMinLoc = g.getUniformLocation(prog, 'u_shockMin')
        const uTrendMaskLoc = g.getUniformLocation(prog, 'u_trendMask')
        const uGlobalShockFactorLoc = g.getUniformLocation(prog, 'u_GlobalShockFactor')

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
          trendFilter.forEach(t => { mask |= (1 << t) })
          g.uniform1i(uTrendMaskLoc, mask)
        }
        if (uGlobalShockFactorLoc) {
          g.uniform1f(uGlobalShockFactorLoc, globalShockFactorRef.current)
        }

        const stride = useV8Ref.current ? VERTEX28_STRIDE : STRIDE_BYTES
        const bufBytes = bufferDataRef.current?.byteLength ?? 0
        const maxCount = bufBytes > 0 ? Math.floor(bufBytes / stride) : vertexCountRef.current
        let drawCount = vertexCountRef.current
        if (drawCount > maxCount) {
          console.warn('[draw] clamping drawCount to buffer capacity', {
            mode: useV8Ref.current ? 'v8' : 'legacy',
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
  }, [streamUrlBin, onAssetClick])

  // --- DEFINITIVE POLLING: 5/10s, no overlap, no early start ---
  useEffect(() => {
    if (!streamUrlBin) return

    const currentEpoch = ++pollEpochRef.current
    const effectivePollMs = Math.max(2000, pollMs ?? 2000)
    let disposed = false

    // Arming delay: first poll cannot happen earlier than effectivePollMs from NOW
    const armAt = Date.now() + effectivePollMs

    const symbolsUrl = streamUrlSymbols || null

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
      if (!streamUrlBin) return

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
        // V8 mode: use snapshot endpoint (check backoff first)
        if (useV8Ref.current) {
          const now = Date.now()
          if (now < v8NextRetryAtRef.current) {
            // backoff active -> use legacy for this tick
            rebuildPipelineIfNeeded(false)
            const result = await fetchPoints(streamUrlBin, ac.signal)
            if (result === null) {
              // fetchPoints returned null (could be 204 or error)
            } else {
              if (symbolsUrl && !symbolsLoadedRef.current) {
                const symbols = await fetchSymbols(symbolsUrl, ac.signal)
                const symbolStrings = symbols.map((item: any) => item.symbol || `ASSET-${item.id}`)
                symbolsMapRef.current = new Map(symbolStrings.map((s: string, i: number) => [i, s]))
                symbolsLoadedRef.current = true
              }
            }
            return
          }
          
          const ok = await fetchV8Snapshot(ac.signal)
          if (ok === false) {
            // immediate fallback for THIS SAME tick
            rebuildPipelineIfNeeded(false)
            const result = await fetchPoints(streamUrlBin, ac.signal)
            if (result === null) {
              // fetchPoints returned null (could be 204 or error)
            } else {
              if (symbolsUrl && !symbolsLoadedRef.current) {
                const symbols = await fetchSymbols(symbolsUrl, ac.signal)
                const symbolStrings = symbols.map((item: any) => item.symbol || `ASSET-${item.id}`)
                symbolsMapRef.current = new Map(symbolStrings.map((s: string, i: number) => [i, s]))
                symbolsLoadedRef.current = true
              }
            }
            return
          }
          
          // V8 snapshot loaded successfully
          rebuildPipelineIfNeeded(true)
          quantumStatsRef.current.fps = fpsRef.current.fps
          // Clear backoff on success
          v8NextRetryAtRef.current = 0
          // Clear status message on success
          setStats(prev => ({ ...prev, shaderLog: null }))
        } else {
          // Legacy mode: use points.bin (or V8 backoff fallback)
          rebuildPipelineIfNeeded(false)
          const result = await fetchPoints(streamUrlBin, ac.signal)
          
          // Handle 204 No Content: keep app online, preserve previous buffers
          if (result === null) {
            // fetchPoints returned null (could be 204 or error)
            // If it was 204, stats.noData is already set by fetchPoints
            // Do not clear points or set offline state
            // Continue normal polling cadence
          } else {
            // Successful fetch with data: proceed normally
            // ---- KEEP SYMBOL FETCH LOGIC (preserving existing 0-based indexing) ----
            // Only fetch once per mount:
            if (symbolsUrl && !symbolsLoadedRef.current) {
              const symbols = await fetchSymbols(symbolsUrl, ac.signal)
              const symbolStrings = symbols.map((item: any) => item.symbol || `ASSET-${item.id}`)
              symbolsMapRef.current = new Map(symbolStrings.map((s: string, i: number) => [i, s]))
              symbolsLoadedRef.current = true
            }
            // ---------------------------------------------------------
          }
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
  }, [streamUrlBin, streamUrlSymbols, pollMs])

  // V8: WebSocket delta stream (10Hz)
  useEffect(() => {
    if (!useV8Ref.current) return
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/universe/v8/stream`
    
    let ws: WebSocket | null = null
    let reconnectTimeout: number | null = null
    
    const connect = () => {
      try {
        ws = new WebSocket(wsUrl)
        ws.binaryType = 'arraybuffer'
        
        ws.onopen = () => {
          console.log('[V8] WebSocket connected')
          quantumStatsRef.current.lastWSLagMs = 0
        }
        
        ws.onmessage = async (event) => {
          const receiveStart = performance.now()
          try {
            // Decompress Zstd
            const compressed = event.data as ArrayBuffer
            const decompressed = await decompressZstd(compressed)
            
            // Decode MessagePack (simplified - assume it's a delta array)
            // For now, queue for processing in render loop
            deltaQueueRef.current.push(decompressed)
            quantumStatsRef.current.deltaQueueDepth = deltaQueueRef.current.length
            quantumStatsRef.current.lastWSLagMs = Math.round(performance.now() - receiveStart)
          } catch (e) {
            console.error('[V8] WebSocket message processing failed:', e)
          }
        }
        
        ws.onerror = (err) => {
          console.error('[V8] WebSocket error:', err)
        }
        
        ws.onclose = () => {
          console.log('[V8] WebSocket closed, reconnecting...')
          reconnectTimeout = window.setTimeout(connect, 3000)
        }
        
        wsRef.current = ws
      } catch (e) {
        console.error('[V8] WebSocket connection failed:', e)
        reconnectTimeout = window.setTimeout(connect, 5000)
      }
    }
    
    connect()
    
    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout)
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
