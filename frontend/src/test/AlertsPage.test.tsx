import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { AlertsPage } from '../pages/AlertsPage'
import * as client from '../api/client'

vi.mock('../api/client', () => ({
  typedGet: vi.fn(),
  typedPost: vi.fn(),
}))

describe('AlertsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render alerts table', async () => {
    ;(client.typedGet as any).mockImplementation((path: string) => {
      if (path === '/assets') {
        return Promise.resolve([{ id: 1, symbol: 'AAPL', name: 'Apple Inc.' }])
      }
      if (path.includes('/alerts')) {
        return Promise.resolve([
          {
            id: 1,
            asset_id: 1,
            key: 'rsi_high',
            severity: 'warning',
            message: 'RSI14 is high',
            triggered_at: new Date().toISOString(),
            resolved_at: null,
            payload: { rsi: 75 },
          },
        ])
      }
    })

    render(<AlertsPage />)

    await waitFor(() => {
      expect(screen.getByText(/RSI14 is high/)).toBeInTheDocument()
      expect(screen.getByText(/AAPL/)).toBeInTheDocument()
    })
  })

  it('should display filters', async () => {
    ;(client.typedGet as any).mockResolvedValue([])

    render(<AlertsPage />)

    await waitFor(() => {
      expect(screen.getByText(/Status/)).toBeInTheDocument()
      expect(screen.getByText(/Severity/)).toBeInTheDocument()
      expect(screen.getByText(/Asset/)).toBeInTheDocument()
    })
  })

  it('should call resolve endpoint when resolve button clicked', async () => {
    ;(client.typedGet as any).mockImplementation((path: string) => {
      if (path === '/assets') {
        return Promise.resolve([{ id: 1, symbol: 'AAPL' }])
      }
      if (path.includes('/alerts')) {
        return Promise.resolve([
          {
            id: 1,
            asset_id: 1,
            key: 'rsi_high',
            severity: 'warning',
            message: 'RSI14 is high',
            triggered_at: new Date().toISOString(),
            resolved_at: null,
            payload: {},
          },
        ])
      }
    })

    ;(client.typedPost as any).mockResolvedValue({
      id: 1,
      asset_id: 1,
      key: 'rsi_high',
      severity: 'warning',
      message: 'RSI14 is high',
      triggered_at: new Date().toISOString(),
      resolved_at: new Date().toISOString(),
      payload: {},
    })

    render(<AlertsPage />)

    // Wait for resolve button
    const resolveButton = await waitFor(() =>
      screen.getByRole('button', { name: /resolve/i })
    )
    fireEvent.click(resolveButton)

    // Check that typedPost was called
    await waitFor(() => {
      expect(client.typedPost).toHaveBeenCalledWith('/alerts/1/resolve', {})
    })
  })

  it('should display recompute confirmation dialog', async () => {
    ;(client.typedGet as any).mockResolvedValue([])

    render(<AlertsPage />)

    // Click recompute button
    const recomputeButton = await waitFor(() =>
      screen.getByRole('button', { name: /recompute all alerts/i })
    )
    fireEvent.click(recomputeButton)

    // Check that confirmation dialog appears
    await waitFor(() => {
      expect(screen.getByText(/Are you sure/i)).toBeInTheDocument()
    })
  })

  it('should display error on 429 rate limit', async () => {
    ;(client.typedGet as any).mockImplementation((path: string) => {
      if (path === '/assets') return Promise.resolve([])
      if (path.includes('/alerts')) {
        return Promise.reject(new Error('429 Too Many Requests'))
      }
    })

    render(<AlertsPage />)

    await waitFor(() => {
      expect(screen.getByText(/rate limit/i)).toBeInTheDocument()
    })
  })
})
