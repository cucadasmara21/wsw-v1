import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MetricsPage } from '../pages/MetricsPage'
import * as client from '../api/client'

vi.mock('../api/client', () => ({
  typedGet: vi.fn(),
  typedPost: vi.fn(),
}))

describe('MetricsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render asset selector', async () => {
    ;(client.typedGet as any).mockResolvedValue([
      { id: 1, symbol: 'AAPL', name: 'Apple Inc.' },
      { id: 2, symbol: 'MSFT', name: 'Microsoft Corp.' },
    ])

    render(<MetricsPage />)

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument()
    })
  })

  it('should load and display metrics when asset is selected', async () => {
    ;(client.typedGet as any).mockImplementation((path: string) => {
      if (path === '/assets') {
        return Promise.resolve([{ id: 1, symbol: 'AAPL', name: 'Apple Inc.' }])
      }
      if (path.includes('/metrics/1/metrics')) {
        return Promise.resolve({
          id: 1,
          asset_id: 1,
          as_of: new Date().toISOString(),
          metrics: { sma20: 150.25, rsi14: 65.3, volatility: 0.0245 },
          quality: { bars_count: 252, low_data: false },
          explain: {},
          created_at: new Date().toISOString(),
        })
      }
    })

    render(<MetricsPage />)

    // Select asset
    const select = await waitFor(() => screen.getByRole('combobox'))
    fireEvent.change(select, { target: { value: '1' } })

    // Check metrics are displayed
    await waitFor(() => {
      expect(screen.getByText(/SMA20/)).toBeInTheDocument()
      expect(screen.getByText(/150.25/)).toBeInTheDocument()
    })
  })

  it('should call recompute endpoint when button clicked', async () => {
    ;(client.typedGet as any).mockImplementation((path: string) => {
      if (path === '/assets') {
        return Promise.resolve([{ id: 1, symbol: 'AAPL', name: 'Apple Inc.' }])
      }
      if (path.includes('/metrics/1/metrics')) {
        return Promise.resolve({
          id: 1,
          asset_id: 1,
          as_of: new Date().toISOString(),
          metrics: { sma20: 150.0 },
          quality: { bars_count: 100 },
          explain: {},
          created_at: new Date().toISOString(),
        })
      }
    })

    ;(client.typedPost as any).mockResolvedValue({
      id: 1,
      asset_id: 1,
      as_of: new Date().toISOString(),
      metrics: { sma20: 151.0 },
      quality: { bars_count: 101 },
      explain: {},
      created_at: new Date().toISOString(),
    })

    render(<MetricsPage />)

    // Select asset
    const select = await waitFor(() => screen.getByRole('combobox'))
    fireEvent.change(select, { target: { value: '1' } })

    // Click recompute button
    const recomputeButton = await waitFor(() =>
      screen.getByRole('button', { name: /recompute/i })
    )
    fireEvent.click(recomputeButton)

    // Check that typedPost was called
    await waitFor(() => {
      expect(client.typedPost).toHaveBeenCalledWith(
        '/metrics/1/metrics/recompute',
        {}
      )
    })
  })

  it('should display error message on 403', async () => {
    ;(client.typedGet as any).mockImplementation((path: string) => {
      if (path === '/assets') {
        return Promise.resolve([{ id: 1, symbol: 'AAPL', name: 'Apple Inc.' }])
      }
      if (path.includes('/metrics/1/metrics')) {
        return Promise.reject(new Error('403 Forbidden: Access denied'))
      }
    })

    render(<MetricsPage />)

    // Select asset to trigger metrics load
    const select = await waitFor(() => screen.getByRole('combobox'))
    fireEvent.change(select, { target: { value: '1' } })

    await waitFor(() => {
      expect(screen.getByText(/access denied/i)).toBeInTheDocument()
    })
  })
})
