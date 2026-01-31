import { useEffect, useRef, useState } from 'react'
import { apiClient } from '../lib/api'

interface PointsData {
  // Route A: Vertex28 (ArrayBuffer)
  buf: ArrayBuffer
}

const VERTEX_SHADER = `#version 300 es
in uint aPosPacked;
in uint aTaxonomy32;
in uint aMeta32;

uniform vec2 uViewport;
uniform float uTime;

out vec4 vColor;
out float vAlpha;

void main() {
  // Unpack position
  float x = float((aPosPacked >> 16u) & 0xFFFFu) / 65535.0;
  float y = float(aPosPacked & 0xFFFFu) / 65535.0;
  
  // Unpack taxonomy32: [monolith8 | cluster8 | subcluster8 | variant8]
  uint monolith = (aTaxonomy32 >> 24u) & 0xFFu;
  
  // Unpack meta32: [risk8 | shock8 | temporal8 | flags8]
  uint risk8 = (aMeta32 >> 24u) & 0xFFu;
  uint flags8 = aMeta32 & 0xFFu;
  bool highRisk = (flags8 & 0x01u) != 0u;
  bool outlier = (flags8 & 0x04u) != 0u;
  
  // Color by monolith (6 monoliths)
  vec3 palette[6];
  palette[0] = vec3(0.2, 0.4, 0.8);  // Blue
  palette[1] = vec3(0.8, 0.2, 0.4);  // Red
  palette[2] = vec3(0.2, 0.8, 0.4);  // Green
  palette[3] = vec3(0.8, 0.6, 0.2);  // Orange
  palette[4] = vec3(0.6, 0.2, 0.8);  // Purple
  palette[5] = vec3(0.4, 0.8, 0.8);  // Cyan
  
  uint monolithIdx = min(monolith, 5u);
  vec3 baseColor = palette[monolithIdx];
  
  // Luminosity by risk
  float risk = float(risk8) / 255.0;
  float luminosity = 0.3 + 0.7 * risk;
  vColor = vec4(baseColor * luminosity, 1.0);
  
  // Outlier pulse
  if (outlier) {
    vAlpha = 0.5 + 0.5 * sin(uTime * 3.0);
  } else {
    vAlpha = 1.0;
  }
  
  // Transform to clip space
  vec2 pos = (vec2(x, y) * 2.0 - 1.0) * vec2(1.0, -1.0);
  gl_Position = vec4(pos, 0.0, 1.0);
  gl_PointSize = highRisk ? 3.0 : 2.0;
}
`

const FRAGMENT_SHADER = `#version 300 es
precision highp float;

in vec4 vColor;
in float vAlpha;

out vec4 fragColor;

void main() {
  vec2 coord = gl_PointCoord - vec2(0.5);
  float dist = length(coord);
  if (dist > 0.5) discard;
  
  float alpha = vAlpha * (1.0 - smoothstep(0.3, 0.5, dist));
  fragColor = vec4(vColor.rgb, alpha);
}
`

export function UniverseCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [points, setPoints] = useState<PointsData | null>(null)
  const [loading, setLoading] = useState(true)
  const glRef = useRef<WebGL2RenderingContext | null>(null)
  const programRef = useRef<WebGLProgram | null>(null)
  const buffersRef = useRef<{ posPacked: WebGLBuffer | null; taxonomy32: WebGLBuffer | null; meta32: WebGLBuffer | null }>({
    posPacked: null,
    taxonomy32: null,
    meta32: null
  })
  const timeRef = useRef(0)

  useEffect(() => {
    async function loadPoints() {
      try {
        const url = '/api/universe/v8/snapshot?format=vertex28&compression=none'
        const resp = await fetch(url)
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const buf = await resp.arrayBuffer()
        if (buf.byteLength % 28 !== 0) throw new Error(`Vertex28 stride violation: ${buf.byteLength}`)
        setPoints({ buf })
      } catch (err) {
        console.error('Failed to load points:', err)
      } finally {
        setLoading(false)
      }
    }
    loadPoints()
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !points) return

    const gl = canvas.getContext('webgl2')
    if (!gl) {
      console.error('WebGL2 not supported')
      return
    }

    glRef.current = gl

    // Create shaders
    function createShader(type: number, source: string): WebGLShader | null {
      const shader = gl.createShader(type)
      if (!shader) return null
      gl.shaderSource(shader, source)
      gl.compileShader(shader)
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.error('Shader compile error:', gl.getShaderInfoLog(shader))
        gl.deleteShader(shader)
        return null
      }
      return shader
    }

    const vs = createShader(gl.VERTEX_SHADER, VERTEX_SHADER)
    const fs = createShader(gl.FRAGMENT_SHADER, FRAGMENT_SHADER)
    if (!vs || !fs) return

    const program = gl.createProgram()
    if (!program) return
    gl.attachShader(program, vs)
    gl.attachShader(program, fs)
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error('Program link error:', gl.getProgramInfoLog(program))
      return
    }

    programRef.current = program

    // Get attribute locations
    const aPosPackedLoc = gl.getAttribLocation(program, 'aPosPacked')
    const aTaxonomy32Loc = gl.getAttribLocation(program, 'aTaxonomy32')
    const aMeta32Loc = gl.getAttribLocation(program, 'aMeta32')
    const uViewportLoc = gl.getUniformLocation(program, 'uViewport')
    const uTimeLoc = gl.getUniformLocation(program, 'uTime')

    // Create buffers
    const posPackedBuffer = gl.createBuffer()
    const taxonomy32Buffer = gl.createBuffer()
    const meta32Buffer = gl.createBuffer()

    buffersRef.current = {
      posPacked: posPackedBuffer,
      taxonomy32: taxonomy32Buffer,
      meta32: meta32Buffer
    }

    // Upload data (legacy packed arrays removed; this component is kept as a minimal V8 viewer)
    const n = Math.floor(points.buf.byteLength / 28)
    const view = new DataView(points.buf)
    const posPackedData = new Uint32Array(n)
    const taxonomy32Data = new Uint32Array(n)
    const meta32Data = new Uint32Array(n)
    for (let i = 0; i < n; i++) {
      const off = i * 28
      const x = view.getFloat32(off + 8, true)
      const y = view.getFloat32(off + 12, true)
      const tax = view.getUint32(off + 0, true) // morton_u32 used as stable domain key here
      const meta = view.getUint32(off + 4, true)
      const xu16 = Math.max(0, Math.min(65535, Math.floor(x * 65535)))
      const yu16 = Math.max(0, Math.min(65535, Math.floor(y * 65535)))
      posPackedData[i] = ((xu16 & 0xffff) << 16) | (yu16 & 0xffff)
      taxonomy32Data[i] = tax >>> 0
      meta32Data[i] = meta >>> 0
    }

    gl.bindBuffer(gl.ARRAY_BUFFER, posPackedBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, posPackedData, gl.STATIC_DRAW)

    gl.bindBuffer(gl.ARRAY_BUFFER, taxonomy32Buffer)
    gl.bufferData(gl.ARRAY_BUFFER, taxonomy32Data, gl.STATIC_DRAW)

    gl.bindBuffer(gl.ARRAY_BUFFER, meta32Buffer)
    gl.bufferData(gl.ARRAY_BUFFER, meta32Data, gl.STATIC_DRAW)

    // Render loop
    function render() {
      if (!gl || !program) return

      gl.useProgram(program)
      gl.viewport(0, 0, canvas.width, canvas.height)
      gl.clearColor(0.05, 0.05, 0.1, 1.0)
      gl.clear(gl.COLOR_BUFFER_BIT)
      gl.enable(gl.BLEND)
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)

      // Set uniforms
      gl.uniform2f(uViewportLoc, canvas.width, canvas.height)
      timeRef.current += 0.016
      gl.uniform1f(uTimeLoc, timeRef.current)

      // Bind attributes
      gl.bindBuffer(gl.ARRAY_BUFFER, posPackedBuffer)
      gl.enableVertexAttribArray(aPosPackedLoc)
      gl.vertexAttribIPointer(aPosPackedLoc, 1, gl.UNSIGNED_INT, 0, 0)

      gl.bindBuffer(gl.ARRAY_BUFFER, taxonomy32Buffer)
      gl.enableVertexAttribArray(aTaxonomy32Loc)
      gl.vertexAttribIPointer(aTaxonomy32Loc, 1, gl.UNSIGNED_INT, 0, 0)

      gl.bindBuffer(gl.ARRAY_BUFFER, meta32Buffer)
      gl.enableVertexAttribArray(aMeta32Loc)
      gl.vertexAttribIPointer(aMeta32Loc, 1, gl.UNSIGNED_INT, 0, 0)

      // Draw
      gl.drawArrays(gl.POINTS, 0, n)

      requestAnimationFrame(render)
    }

    render()

    return () => {
      gl.deleteProgram(program)
      gl.deleteShader(vs)
      gl.deleteShader(fs)
      if (posPackedBuffer) gl.deleteBuffer(posPackedBuffer)
      if (taxonomy32Buffer) gl.deleteBuffer(taxonomy32Buffer)
      if (meta32Buffer) gl.deleteBuffer(meta32Buffer)
    }
  }, [points])

  if (loading) {
    return <div style={{ padding: '2rem' }}>Loading point cloud...</div>
  }

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <canvas
        ref={canvasRef}
        width={1920}
        height={1080}
        style={{ width: '100%', height: '100%', display: 'block' }}
      />
    </div>
  )
}
