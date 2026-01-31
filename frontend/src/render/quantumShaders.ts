/**
 * Titan V8 Quantum Shaders (Luminous Singularity)
 * Vertex28 format: <IIfffff (28 bytes)
 * Orange core for high-fidelity, Cyan vertical columns for outliers
 */

export const TITAN_V8_VERTEX_SHADER = `#version 300 es
precision highp float;
precision highp int;

layout(location=0) in vec3 a_position;
layout(location=1) in float a_risk;
layout(location=2) in float a_shock;
layout(location=3) in uint a_morton;
layout(location=4) in uint a_meta;

uniform float u_pointSize;
uniform float u_time;
uniform float u_zoom;
uniform vec2 u_pan;
uniform mat4 u_projection;
uniform mat4 u_view;
uniform vec3 u_cameraPos;

out vec4 v_color;
out float v_risk;
out float v_shock;
out float v_outlier;

// Route A: interpret meta32 bit 5 as outlier marker (meta32_minimal)
bool is_outlier(uint meta) {
  return ((meta >> 5u) & 1u) == 1u;
}

void main() {
  vec3 pos = a_position;
  
  // Apply shock animation (subtle rotation around Z)
  float spinAngle = a_shock * u_time * 0.5;
  float cosSpin = cos(spinAngle);
  float sinSpin = sin(spinAngle);
  pos.xy = mat2(cosSpin, -sinSpin, sinSpin, cosSpin) * pos.xy;
  
  // Transform to clip space
  vec4 clipPos = u_projection * u_view * vec4(pos, 1.0);
  gl_Position = clipPos;
  
  // Point size based on risk and distance (P-01: EPS_DIST guard, no NaN/Inf)
  const float EPS_DIST = 1e-9;
  float dist = max(EPS_DIST, length(u_cameraPos - pos));
  float baseSize = u_pointSize * (1.0 + a_risk * 2.0);
  gl_PointSize = baseSize / max(1.0, dist * 0.1);
  
  v_risk = a_risk;
  v_shock = a_shock;
  v_outlier = is_outlier(a_meta) ? 1.0 : 0.0;
  
  // Base color intensity from risk
  float intensity = 0.5 + a_risk * 1.5;
  v_color = vec4(intensity, intensity * 0.6, 0.0, 1.0); // Orange base
}
`

export const TITAN_V8_FRAGMENT_SHADER = `#version 300 es
precision highp float;

in vec4 v_color;
in float v_risk;
in float v_shock;
in float v_outlier;

out vec4 outColor;

void main() {
  vec2 uv = gl_PointCoord * 2.0 - 1.0;
  float r2 = dot(uv, uv);
  if (r2 > 1.0) discard;
  
  // Base glow (Gaussian falloff)
  float glow = smoothstep(1.0, 0.0, r2);
  
  // Color selection
  vec3 baseColor;
  if (v_outlier > 0.5) {
    // Cyan vertical column for outliers (anisotropic Gaussian)
    float verticalStretch = 1.0 + v_outlier * 2.0;
    float distY = abs(uv.y) * verticalStretch;
    float distX = abs(uv.x);
    float r2Aniso = distX * distX + distY * distY;
    glow = smoothstep(1.0, 0.0, r2Aniso);
    baseColor = vec3(0.0, 0.8, 1.0); // Cyan
  } else {
    // Orange core for high-fidelity
    baseColor = vec3(1.0, 0.5, 0.0); // Orange
    // Enhance intensity for high risk
    baseColor *= (0.7 + v_risk * 0.3);
  }
  
  float alpha = glow * v_color.a * (0.6 + v_risk * 0.4);
  outColor = vec4(baseColor, alpha);
}
`

export const PICKING_VERTEX_SHADER = `#version 300 es
precision highp float;

layout(location=0) in vec3 a_position;
layout(location=5) in float a_pickId; // Encoded ID

uniform mat4 u_projection;
uniform mat4 u_view;
uniform float u_pointSize;

void main() {
  vec4 clipPos = u_projection * u_view * vec4(a_position, 1.0);
  gl_Position = clipPos;
  gl_PointSize = u_pointSize;
}
`

export const PICKING_FRAGMENT_SHADER = `#version 300 es
precision highp float;

in float a_pickId;
out vec4 outColor;

void main() {
  vec2 uv = gl_PointCoord * 2.0 - 1.0;
  float r2 = dot(uv, uv);
  if (r2 > 1.0) discard;
  
  // Encode ID to RGB (24-bit)
  float id = a_pickId;
  float r = floor(id / 65536.0) / 255.0;
  float g = floor(mod(id, 65536.0) / 256.0) / 255.0;
  float b = mod(id, 256.0) / 255.0;
  
  outColor = vec4(r, g, b, 1.0);
}
`
