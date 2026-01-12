import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { OverviewPage } from '../pages/OverviewPage'
import * as client from '../api/client'

// Mock the API client
vi.mock('../api/client', () => ({
  getCategorySelectionCurrent: vi.fn(),
  recomputeCategorySelection: vi.fn(),
  getLeaderboard: vi.fn(),
  listAlerts: vi.fn(),
}))

// Mock apiClient
vi.mock('../lib/api', () => ({
  apiClient: {
    get: vi.fn(),
  },
}))

describe('OverviewPage Selection Widget', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a table with selected assets and displays score', async () => {
    const { apiClient } = await import('../lib/api')
    ;(apiClient.get as any).mockResolvedValueOnce([]) // assets
    ;(apiClient.get as any).mockResolvedValueOnce({
      // tree with categories
      groups: [
        {
          id: 1,
          name: 'Test Group',
          subgroups: [
            {
              id: 1,
              name: 'Test Subgroup',
              categories: [{ id: 1, name: 'Test Category' }],
            },
          ],
        },
      ],
    })

    ;(client.getCategorySelectionCurrent as any).mockResolvedValueOnce({
      selected: [
        {
          asset_id: 1,
          symbol: 'AAPL',
          name: 'Apple Inc',
          score: 0.85,
          rank: 1,
          data_meta: { cached: true, stale: false },
        },
        {
          asset_id: 2,
          symbol: 'MSFT',
          name: 'Microsoft',
          score: 0.72,
          rank: 2,
          data_meta: { cached: true, stale: false },
        },
      ],
    })

    ;(client.getLeaderboard as any).mockResolvedValueOnce([])
    ;(client.listAlerts as any).mockResolvedValueOnce([])

    render(
      <BrowserRouter>
        <OverviewPage />
      </BrowserRouter>
    )

    // Wait for the selection widget to load
    await waitFor(() => {
      expect(screen.getByText('Top Selected Assets')).toBeInTheDocument()
    })

    // Check that assets are rendered
    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument()
      expect(screen.getByText('MSFT')).toBeInTheDocument()
    })

    // Check that scores are displayed
    expect(screen.getByText('85.0')).toBeInTheDocument()
    expect(screen.getByText('72.0')).toBeInTheDocument()
  })

  it('clicking Recompute calls POST and refreshes selection', async () => {
    const { apiClient } = await import('../lib/api')
    ;(apiClient.get as any).mockResolvedValueOnce([])
    ;(apiClient.get as any).mockResolvedValueOnce({
      groups: [
        {
          id: 1,
          name: 'Test Group',
          subgroups: [
            {
              id: 1,
              name: 'Test Subgroup',
              categories: [{ id: 1, name: 'Test Category' }],
            },
          ],
        },
      ],
    })

    ;(client.getCategorySelectionCurrent as any).mockResolvedValueOnce({
      selected: [
        {
          asset_id: 1,
          symbol: 'AAPL',
          name: 'Apple Inc',
          score: 0.85,
          rank: 1,
        },
      ],
    })

    ;(client.recomputeCategorySelection as any).mockResolvedValueOnce({
      selected: [
        {
          asset_id: 2,
          symbol: 'MSFT',
          name: 'Microsoft',
          score: 0.90,
          rank: 1,
        },
      ],
    })

    ;(client.getLeaderboard as any).mockResolvedValueOnce([])
    ;(client.listAlerts as any).mockResolvedValueOnce([])

    render(
      <BrowserRouter>
        <OverviewPage />
      </BrowserRouter>
    )

    // Wait for initial load
    await waitFor(() => {
      expect(screen.getByText('Top Selected Assets')).toBeInTheDocument()
    })

    // Mock window.confirm
    vi.spyOn(window, 'confirm').mockReturnValueOnce(true)

    // Click Recompute button
    const recomputeButton = await screen.findByText('Recompute')
    await userEvent.click(recomputeButton)

    // Verify that recompute was called with correct parameters
    await waitFor(() => {
      expect(client.recomputeCategorySelection).toHaveBeenCalledWith(1, 10, 90)
    })

    // Verify that the new selection is displayed
    await waitFor(() => {
      expect(screen.getByText('MSFT')).toBeInTheDocument()
      expect(screen.getByText('90.0')).toBeInTheDocument()
    })
  })

  it('displays 429 error message when rate limited', async () => {
    const { apiClient } = await import('../lib/api')
    ;(apiClient.get as any).mockResolvedValueOnce([])
    ;(apiClient.get as any).mockResolvedValueOnce({
      groups: [
        {
          id: 1,
          name: 'Test Group',
          subgroups: [
            {
              id: 1,
              name: 'Test Subgroup',
              categories: [{ id: 1, name: 'Test Category' }],
            },
          ],
        },
      ],
    })

    ;(client.getCategorySelectionCurrent as any).mockRejectedValueOnce(
      new Error('429 Too Many Requests')
    )

    ;(client.getLeaderboard as any).mockResolvedValueOnce([])
    ;(client.listAlerts as any).mockResolvedValueOnce([])

    render(
      <BrowserRouter>
        <OverviewPage />
      </BrowserRouter>
    )

    // Wait for error message
    await waitFor(() => {
      expect(
        screen.getByText('Rate limited. Please try again in a moment.')
      ).toBeInTheDocument()
    })
  })

  it('displays empty state when no assets selected', async () => {
    const { apiClient } = await import('../lib/api')
    ;(apiClient.get as any).mockResolvedValueOnce([])
    ;(apiClient.get as any).mockResolvedValueOnce({
      groups: [
        {
          id: 1,
          name: 'Test Group',
          subgroups: [
            {
              id: 1,
              name: 'Test Subgroup',
              categories: [{ id: 1, name: 'Test Category' }],
            },
          ],
        },
      ],
    })

    ;(client.getCategorySelectionCurrent as any).mockResolvedValueOnce({
      selected: [],
    })

    ;(client.getLeaderboard as any).mockResolvedValueOnce([])
    ;(client.listAlerts as any).mockResolvedValueOnce([])

    render(
      <BrowserRouter>
        <OverviewPage />
      </BrowserRouter>
    )

    // Wait for empty state message
    await waitFor(() => {
      expect(
        screen.getByText(
          'No selected assets yet. Click "Recompute" to generate.'
        )
      ).toBeInTheDocument()
    })
  })
})
