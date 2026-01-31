/**
 * Vertex28 stride validation. FAIL_FAST on violation.
 * Used by pointsWorker before parsing; also testable.
 */
export const VERTEX28_STRIDE = 28

export function validateVertex28Buffer(buf: ArrayBuffer): void {
  if (buf.byteLength % 28 !== 0) {
    throw new Error('FAIL_FAST: STRIDE_28_VIOLATION')
  }
}
