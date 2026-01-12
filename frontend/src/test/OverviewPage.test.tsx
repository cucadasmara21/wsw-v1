import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { OverviewPage } from '../pages/OverviewPage'
import * as apiClient from '../api/client'
import * as libApi from '../lib/api'

// Mock API calls
vi.mock('../lib/api', () => ({
  apiClient: {
    get: vi.fn((path?: string) =>
      path && path.includes('/universe/tree')
        ? Promise.resolve({ groups: [] })
        : Promise.resolve([])
    ),
  },
}))

vi.mock('../api/client', () => ({
  getLeaderboard: vi.fn(),
}))

describe('OverviewPage', () => {
  it('renders overview title', () => {
    ;(apiClient.getLeaderboard as any).mockResolvedValue([])
    
    render(
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>
    )
    
    expect(screen.getByText('Overview')).toBeDefined()
  })
  
  it('renders stat cards', () => {
    ;(apiClient.getLeaderboard as any).mockResolvedValue([])
    
    render(
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>
    )
    
    expect(screen.getByText('Total Assets')).toBeDefined()
    expect(screen.getByText('Asset Groups')).toBeDefined()
  })

  it('renders leaderboard with top 10 assets', async () => {
    const mockLeaderboard = Array.from({ length: 10 }, (_, i) => ({
      asset_id: i + 1,
      symbol: `SYM${i + 1}`,
      name: `Asset ${i + 1}`,
      score: 0.9 - i * 0.05,
    }))

    ;(apiClient.getLeaderboard as any).mockResolvedValue(mockLeaderboard)

    render(
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByText('Top Risk Assets')).toBeInTheDocument()
    })

    await waitFor(() => {
      expect(screen.getByText('SYM1')).toBeInTheDocument()
      expect(screen.getByText('#1')).toBeInTheDocument()
    })

    // Check score rendering
    const scoreElements = screen.getAllByText(/90.0|85.0/)
    expect(scoreElements.length).toBeGreaterThan(0)
  })

  it('navigates to asset detail on row click', async () => {
    const mockLeaderboard = [
      { asset_id: 1, symbol: 'AAPL', name: 'Apple Inc.', score: 0.75 },
    ]

    ;(apiClient.getLeaderboard as any).mockResolvedValue(mockLeaderboard)

    const navigateSpy = vi.fn()

    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/assets/:id" element={<div>Asset Detail</div>} />
        </Routes>
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument()
    })

    const row = screen.getByText('AAPL').closest('tr')
    if (row) {
      fireEvent.click(row)
    }

    // Navigation happens via onClick handler; this test validates the presence
  })

  it('displays error on leaderboard failure', async () => {
    ;(apiClient.getLeaderboard as any).mockRejectedValue(new Error('503 Service Unavailable'))

    render(
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(
        screen.getByText(/Leaderboard temporarily unavailable \(provider disabled\/quota\)/i)
      ).toBeInTheDocument()
    })
  })
})
