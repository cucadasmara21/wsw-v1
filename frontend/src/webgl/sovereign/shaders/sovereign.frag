// sovereign.frag
// Fragment shader for Sovereign Mode visualization
// Applies visual effects based on risk and outlier status

#version 300 es
precision highp float;

in vec4 v_color;
in float v_risk;
in float v_distance;
flat in int v_domain;
flat in bool v_is_outlier;

out vec4 fragColor;

void main() {
  // Base color from vertex shader
  vec4 color = v_color;
  
  // Glow effect for high risk (risk > 0.8)
  if (v_risk > 0.8) {
    float glow = (v_risk - 0.8) * 5.0;
    color.rgb += glow * vec3(0.5, 0.3, 0.0);  // Amber glow
  }
  
  // Soft edge for point sprites
  vec2 coord = gl_PointCoord - vec2(0.5);
  float dist = length(coord);
  float edgeAlpha = smoothstep(0.5, 0.4, dist);
  
  // Final color with edge alpha
  fragColor = vec4(color.rgb, color.a * edgeAlpha);
  
  // Discard very transparent fragments for performance
  if (fragColor.a < 0.01) {
    discard;
  }
}
