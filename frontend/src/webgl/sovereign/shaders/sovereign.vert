// sovereign.vert
// Vertex shader for Sovereign Mode visualization
// Decodes 32-bit taxonomy bitmask and applies visual semantics

#version 300 es
precision highp float;

// Instance attributes (from interleaved buffer)
in vec3 a_position;
in float a_size;
in uint a_taxonomy_mask;  // 32-bit bitmask: [3-bit Domain | 1-bit Outlier | 16-bit Risk | 12-bit Reserved]

// Uniforms
uniform mat4 u_modelViewProjection;
uniform vec3 u_cameraPosition;
uniform float u_time;

// Output to fragment shader
out vec4 v_color;
out float v_risk;
out float v_distance;
flat out int v_domain;
flat out bool v_is_outlier;

// Domain color palette (6 domains)
const vec3 DOMAIN_PALETTE[6] = vec3[](
  vec3(0.0, 0.1, 0.3),   // Deep Cobalt - Domain 0: Credit & Liquidity
  vec3(0.0, 1.0, 1.0),   // Electric Cyan - Domain 1: Market & Valuation
  vec3(1.0, 0.5, 0.0),   // Warning Orange - Domain 2: Operational & Tech
  vec3(0.8, 0.0, 0.0),   // Crimson Forensic - Domain 3: Systemic
  vec3(0.5, 0.0, 0.5),   // Sovereign Purple - Domain 4: Geopolitical
  vec3(0.0, 0.8, 0.0)    // Quantum Green - Domain 5: Environmental
);

/**
 * Decode bitmask semantics (EXACT match with Python/TypeScript).
 * Contract: [3-bit Domain | 1-bit Outlier | 16-bit Risk | 12-bit Reserved]
 */
void decodeBitmaskSemantics(uint mask, out vec3 color, out float alpha, out float risk) {
  // Extract components according to contract
  uint domain = mask & 0x7u;                    // bits 0-2
  uint outlier = (mask >> 3u) & 0x1u;          // bit 3
  uint risk16 = (mask >> 4u) & 0xFFFFu;        // bits 4-19
  
  // Normalize risk to 0.0-1.0
  risk = float(risk16) / 65535.0;
  
  // Get base color from domain palette
  color = DOMAIN_PALETTE[int(domain)];
  
  // Apply luminosity based on risk (0.3 + 0.7 * risk)
  float luminosity = 0.3 + 0.7 * risk;
  color *= luminosity;
  
  // Alpha: outliers pulse at ~3Hz, normal = 1.0
  if (outlier == 1u) {
    float pulse = sin(u_time * 3.0 * 3.14159) * 0.3 + 0.7;
    alpha = 0.6 * pulse;
  } else {
    alpha = 1.0;
  }
  
  // Pass to fragment shader
  v_domain = int(domain);
  v_is_outlier = (outlier == 1u);
  v_risk = risk;
}

void main() {
  // Decode bitmask
  vec3 color;
  float alpha, risk;
  decodeBitmaskSemantics(a_taxonomy_mask, color, alpha, risk);
  
  // Calculate distance to camera for LOD (P-01: EPS_DIST guard before division)
  const float EPS_DIST = 1e-9;
  v_distance = max(EPS_DIST, distance(a_position, u_cameraPosition));
  
  // Final color with alpha
  v_color = vec4(color, alpha);
  
  // Transform position
  gl_Position = u_modelViewProjection * vec4(a_position, 1.0);
  
  // Point size with distance-based scaling (P-01: v_distance already guarded)
  gl_PointSize = a_size * (10.0 / v_distance);
}
