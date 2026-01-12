import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AssetDetailPage } from '../pages/AssetDetailPage'
import * as apiClient from '../api/client'
import * as libApi from '../lib/api'

vi.mock('../api/client', () => ({
  getLatestMetrics: vi.fn(),
  recomputeMetrics: vi.fn(),
}))

vi.mock('../lib/api', () => ({
  apiClient: {
    get: vi.fn(),
  },
}))

describe('AssetDetailPage - Metrics', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render metrics score and top 3 drivers', async () => {
    const mockAsset = {
      id: 1,
      symbol: 'AAPL',
      name: 'Apple Inc.',
      sector: 'Technology',
      exchange: 'NASDAQ',
      country: 'US',
      is_active: true,
      created_at: '2024-01-01T00:00:00Z',
    }

    const mockMetrics = {
      id: 1,
      asset_id: 1,
      as_of: '2024-01-10T12:00:00Z',
      metrics: { sma_20: 150.0, rsi_14: 65.0 },
      score: 0.75,
      explain: {
        items: [
          { metric_id: 'rsi_14', raw_value: 65.0, normalized_score: 0.65, weight: 0.25, contribution: 0.1625 },
          { metric_id: 'volatility_20d', raw_value: 0.025, normalized_score: 0.25, weight: 0.25, contribution: 0.0625 },
          { metric_id: 'max_drawdown_90d', raw_value: -0.10, normalized_score: 0.10, weight: 0.30, contribution: 0.03 },
        ],
      },
      created_at: '2024-01-10T12:00:00Z',
    }

    ;(libApi.apiClient.get as any).mockResolvedValue(mockAsset)
    ;(apiClient.getLatestMetrics as any).mockResolvedValue(mockMetrics)

    render(
      <MemoryRouter initialEntries={['/assets/1']}>
        <Routes>
          <Route path="/assets/:id" element={<AssetDetailPage />} />
        </Routes>
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByText(/Score: 75.0/)).toBeInTheDocument()
    })

    expect(screen.getByText(/Top 3 Drivers/)).toBeInTheDocument()
    expect(screen.getByText(/rsi_14/)).toBeInTheDocument()
  })

  it('should call recompute and refresh metrics', async () => {
    const mockAsset = {
      id: 1,
      symbol: 'AAPL',
      name: 'Apple Inc.',
      sector: 'Technology',
      is_active: true,
      created_at: '2024-01-01T00:00:00Z',
    }

    const initialMetrics = {
      id: 1,
      asset_id: 1,
      as_of: '2024-01-10T12:00:00Z',
      metrics: {},
      score: 0.5,
      explain: { items: [] },
      created_at: '2024-01-10T12:00:00Z',
    }

    const recomputedMetrics = {
      ...initialMetrics,
      score: 0.8,
      as_of: '2024-01-10T13:00:00Z',
    }

    ;(libApi.apiClient.get as any).mockResolvedValue(mockAsset)
    ;(apiClient.getLatestMetrics as any).mockResolvedValue(initialMetrics)
    ;(apiClient.recomputeMetrics as any).mockResolvedValue(recomputedMetrics)

    render(
      <MemoryRouter initialEntries={['/assets/1']}>
        <Routes>
          <Route path="/assets/:id" element={<AssetDetailPage />} />
        </Routes>
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByText(/Score: 50.0/)).toBeInTheDocument()
    })

    const recomputeButton = screen.getByRole('button', { name: /Recompute/i })
    fireEvent.click(recomputeButton)

    await waitFor(() => {
      expect(apiClient.recomputeMetrics).toHaveBeenCalledWith(1)
    })

    await waitFor(() => {
      expect(screen.getByText(/Metrics recomputed successfully/i)).toBeInTheDocument()
    })

    await waitFor(() => {
      expect(screen.getByText(/Score: 80.0/)).toBeInTheDocument()
    })
  })

  it('should display 503 error message', async () => {
    const mockAsset = {
      id: 1,
      symbol: 'AAPL',
      name: 'Apple Inc.',
      is_active: true,
      created_at: '2024-01-01T00:00:00Z',
    }

    ;(libApi.apiClient.get as any).mockResolvedValue(mockAsset)
    ;(apiClient.getLatestMetrics as any).mockRejectedValue(
      new Error('503 Service Unavailable')
    )

    render(
      <MemoryRouter initialEntries={['/assets/1']}>
        <Routes>
          <Route path="/assets/:id" element={<AssetDetailPage />} />
        </Routes>
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(
        screen.getByText(/Metrics temporarily unavailable \(provider disabled\/quota\)/i)
      ).toBeInTheDocument()
    })
  })
})
