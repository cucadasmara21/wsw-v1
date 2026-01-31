/**
 * Canonical 32-bit Taxonomy Bitmask Decoder (TypeScript Truth)
 * Contract: [3-bit Domain | 1-bit Outlier | 16-bit Risk Score | 12-bit Reserved]
 * 
 * This MUST match engines/bitmask_encoder.py exactly.
 * 
 * Unpacking formula:
 *   domain   = mask & 0x7
 *   outlier  = (mask >> 3) & 0x1
 *   risk16   = (mask >> 4) & 0xFFFF
 *   risk01   = risk16 / 65535.0
 */

export interface TaxonomyComponents {
  domain: number;      // 0-5
  outlier: number;     // 0 or 1
  risk01: number;      // 0.0-1.0
  risk16: number;      // 0-65535 (raw)
}

export interface SemanticVisualAttributes {
  baseColor: [number, number, number];  // RGB according to domain palette
  alpha: number;                        // Transparency (outlier pulses)
  luminosity: number;                   // Brightness based on risk
  saturation: number;                   // Color saturation
  domainId: number;
  isOutlier: boolean;
  riskPercent: number;
}

export class BitmaskSemanticDecoder {
  /**
   * Decode a single 32-bit bitmask into taxonomy components.
   * 
   * Contract: EXACT match with Python unpack_taxonomy_mask()
   */
  static decode(mask: number): TaxonomyComponents {
    const domain = mask & 0x7;
    const outlier = (mask >>> 3) & 0x1;
    const risk16 = (mask >>> 4) & 0xFFFF;
    const risk01 = risk16 / 65535.0;
    
    return { domain, outlier, risk01, risk16 };
  }
  
  /**
   * Decode bitmask into visual attributes for WebGL rendering.
   */
  static decodeVisual(mask: number): SemanticVisualAttributes {
    const { domain, outlier, risk01 } = this.decode(mask);
    
    // Domain color palette (6 domains)
    const palette: [number, number, number][] = [
      [0.0, 0.1, 0.3],   // Deep Cobalt - Domain 0: Credit & Liquidity
      [0.0, 1.0, 1.0],   // Electric Cyan - Domain 1: Market & Valuation
      [1.0, 0.5, 0.0],   // Warning Orange - Domain 2: Operational & Tech
      [0.8, 0.0, 0.0],   // Crimson Forensic - Domain 3: Systemic
      [0.5, 0.0, 0.5],   // Sovereign Purple - Domain 4: Geopolitical
      [0.0, 0.8, 0.0],   // Quantum Green - Domain 5: Environmental
    ];
    
    const baseColor = palette[domain] || palette[0];
    
    // Alpha: outliers pulse (handled in shader), normal = 1.0
    const alpha = outlier ? 0.6 : 1.0;
    
    // Luminosity: 0.3 + 0.7 * risk01 (higher risk = brighter)
    const luminosity = 0.3 + 0.7 * risk01;
    
    // Saturation: 0.5 + 0.5 * risk01 (higher risk = more saturated)
    const saturation = 0.5 + 0.5 * risk01;
    
    return {
      baseColor,
      alpha,
      luminosity,
      saturation,
      domainId: domain,
      isOutlier: outlier === 1,
      riskPercent: Math.round(risk01 * 1000) / 10,
    };
  }
  
  /**
   * Batch decode for performance (10k+ assets).
   */
  static decodeBatch(masks: Uint32Array): SemanticVisualAttributes[] {
    const results: SemanticVisualAttributes[] = new Array(masks.length);
    for (let i = 0; i < masks.length; i++) {
      results[i] = this.decodeVisual(masks[i]);
    }
    return results;
  }
  
  /**
   * Generate WebGL attribute buffer from bitmasks.
   * Output: [R, G, B, A, Luminosity, Saturation, Domain, Outlier, Risk]
   * Stride: 9 floats = 36 bytes per instance
   */
  static toWebGLAttributes(masks: Uint32Array): Float32Array {
    const stride = 9;
    const output = new Float32Array(masks.length * stride);
    
    for (let i = 0; i < masks.length; i++) {
      const attrs = this.decodeVisual(masks[i]);
      const offset = i * stride;
      
      output[offset + 0] = attrs.baseColor[0];  // R
      output[offset + 1] = attrs.baseColor[1];  // G
      output[offset + 2] = attrs.baseColor[2];  // B
      output[offset + 3] = attrs.alpha;         // A
      output[offset + 4] = attrs.luminosity;   // Luminosity
      output[offset + 5] = attrs.saturation;    // Saturation
      output[offset + 6] = attrs.domainId;     // Domain
      output[offset + 7] = attrs.isOutlier ? 1.0 : 0.0;  // Outlier
      output[offset + 8] = attrs.riskPercent / 100;      // Risk 0-1
    }
    
    return output;
  }
}
