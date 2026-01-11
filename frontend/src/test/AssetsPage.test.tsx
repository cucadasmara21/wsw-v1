/**
 * Smoke test: AssetsPage component renders
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import AssetsPage from '../pages/AssetsPage'

// Mock fetch globally
global.fetch = vi.fn()

describe('AssetsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading state initially', () => {
    // Mock fetch to never resolve (simulate loading)
    ;(global.fetch as any).mockImplementation(() => new Promise(() => {}))
    
    render(<AssetsPage />)
    expect(screen.getByText(/Loading assets/i)).toBeInTheDocument()
  })

  it('renders assets when fetch succeeds', async () => {
    const mockAssets = [
      { id: 1, symbol: 'AAPL', name: 'Apple Inc.', exchange: 'NASDAQ', country: 'US', is_active: true },
      { id: 2, symbol: 'GOOGL', name: 'Alphabet Inc.', exchange: 'NASDAQ', country: 'US', is_active: true }
    ]

    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockAssets
    })

    render(<AssetsPage />)

    await waitFor(() => {
      expect(screen.getByText(/Assets/i)).toBeInTheDocument()
    })

    // Check that at least one asset symbol is rendered
    await waitFor(() => {
      expect(screen.getByText(/AAPL/i)).toBeInTheDocument()
    })
  })

  it('renders error message when fetch fails', async () => {
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      text: async () => 'Server error'
    })

    render(<AssetsPage />)

    await waitFor(() => {
      expect(screen.getByText(/Error/i)).toBeInTheDocument()
    })
  })
})
