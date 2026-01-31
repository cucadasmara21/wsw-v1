import { describe, it, expect } from 'vitest'
import { validateVertex28Buffer } from '../lib/vertex28Validation'

describe('vertex28Validation', () => {
  it('throws FAIL_FAST: STRIDE_28_VIOLATION for invalid byteLength', () => {
    const buf = new ArrayBuffer(27)
    expect(() => validateVertex28Buffer(buf)).toThrow('FAIL_FAST: STRIDE_28_VIOLATION')
  })
})
