/**
 * Smoke test: API client utility functions
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchApiJson } from '../lib/api'

global.fetch = vi.fn()

describe('API Client', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetchApiJson returns parsed JSON on success', async () => {
    const mockData = { status: 'healthy' }
    
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockData
    })

    const result = await fetchApiJson('/health')
    expect(result).toEqual(mockData)
  })

  it('fetchApiJson throws error on non-ok response', async () => {
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      text: async () => 'Resource not found'
    })

    await expect(fetchApiJson('/nonexistent')).rejects.toThrow(/404/)
  })

  it('constructs correct URL with API base', async () => {
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({})
    })

    await fetchApiJson('/assets')
    
    // Check that fetch was called with correct URL
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/assets'),
      undefined
    )
  })
})
