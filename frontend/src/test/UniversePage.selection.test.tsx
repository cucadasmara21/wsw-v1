/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { UniversePage } from '../pages/UniversePage'
import * as apiClient from '../lib/api'
import * as selectionClient from '../api/client'

vi.mock('../lib/api', () => ({
  apiClient: {
    get: vi.fn(),
  },
}))

vi.mock('../api/client', () => ({
  previewCategorySelection: vi.fn(),
  recomputeCategorySelection: vi.fn(),
}))

describe('UniversePage - Selection Panel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders selection panel when category is selected', async () => {
    // Mock universe tree
    ;(apiClient.apiClient.get as any).mockResolvedValueOnce({
      groups: [
        {
          id: 1,
          name: 'Test Group',
          subgroups: [
            {
              id: 1,
              name: 'Test Subgroup',
              categories: [
                { id: 1, name: 'Test Category' },
              ],
            },
          ],
        },
      ],
    })

    // Mock selection data
    ;(selectionClient.previewCategorySelection as any).mockResolvedValue({
      selected: [
        {
          asset_id: 1,
          symbol: 'AAPL',
          name: 'Apple Inc',
          score: 0.85,
          rank: 1,
          explain: { momentum: 0.3, volatility: 0.25, drawdown: 0.2 },
          data_meta: { cached: true, stale: false, confidence: 0.9 },
        },
        {
          asset_id: 2,
          symbol: 'MSFT',
          name: 'Microsoft',
          score: 0.82,
          rank: 2,
          explain: { liquidity: 0.28, centrality: 0.22 },
          data_meta: { cached: false, stale: false, confidence: 0.95 },
        },
      ],
      meta: {
        category_id: 1,
        category_name: 'Test Category',
        top_n: 10,
        total_candidates: 5,
      },
    })

    // Mock assets
    ;(apiClient.apiClient.get as any).mockResolvedValue([])

    render(
      <MemoryRouter>
        <UniversePage />
      </MemoryRouter>
    )

    // Wait for tree to load
    await waitFor(() => {
      expect(screen.getByText('Test Category')).toBeInTheDocument()
    })

    // Click category to trigger selection load
    const categoryButton = screen.getByText('Test Category')
    categoryButton.click()

    // Wait for selection panel
    await waitFor(() => {
      expect(screen.getByText('Top 10 Selection')).toBeInTheDocument()
    })

    // Check selection table renders
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('MSFT')).toBeInTheDocument()
    expect(screen.getByText('Apple Inc')).toBeInTheDocument()

    // Check top drivers are shown
    expect(screen.getByText(/momentum/i)).toBeInTheDocument()
  })

  it('shows stale badge when data is stale', async () => {
    // Mock universe tree first
    ;(apiClient.apiClient.get as any).mockResolvedValueOnce({
      groups: [
        {
          id: 1,
          name: 'Test Group',
          subgroups: [{ id: 1, name: 'Test Subgroup', categories: [{ id: 1, name: 'Test Category' }] }],
        },
      ],
    })

    // Then mock selection
    ;(selectionClient.previewCategorySelection as any).mockResolvedValue({
      selected: [
        {
          asset_id: 1,
          symbol: 'TST1',
          name: 'Test 1',
          score: 0.5,
          rank: 1,
          explain: {},
          data_meta: { stale: true, cached: true },
        },
      ],
      meta: { category_id: 1, top_n: 10 },
    })

    // Then mock assets
    ;(apiClient.apiClient.get as any).mockResolvedValue([])

    render(
      <MemoryRouter>
        <UniversePage />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByText('Test Category')).toBeInTheDocument()
    })

    screen.getByText('Test Category').click()

    await waitFor(() => {
      expect(screen.getByText(/stale/i)).toBeInTheDocument()
    })
  })

  it('calls recompute endpoint when button clicked', async () => {
    // Mock universe tree first
    ;(apiClient.apiClient.get as any).mockResolvedValueOnce({
      groups: [
        {
          id: 1,
          name: 'Test Group',
          subgroups: [{ id: 1, name: 'Test Subgroup', categories: [{ id: 1, name: 'Test Category' }] }],
        },
      ],
    })

    const mockSelection = {
      selected: [
        {
          asset_id: 1,
          symbol: 'TST1',
          name: 'Test 1',
          score: 0.7,
          rank: 1,
          explain: {},
          data_meta: {},
        },
      ],
      meta: { category_id: 1, top_n: 10 },
    }

    ;(selectionClient.previewCategorySelection as any).mockResolvedValue(mockSelection)
    ;(selectionClient.recomputeCategorySelection as any).mockResolvedValue(mockSelection)

    // Then mock assets
    ;(apiClient.apiClient.get as any).mockResolvedValue([])

    render(
      <MemoryRouter>
        <UniversePage />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByText('Test Category')).toBeInTheDocument()
    })

    screen.getByText('Test Category').click()

    await waitFor(() => {
      expect(screen.getByText('Recompute Selection')).toBeInTheDocument()
    })

    const recomputeButton = screen.getByText('Recompute Selection')
    recomputeButton.click()

    await waitFor(() => {
      expect(selectionClient.recomputeCategorySelection).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ top_n: 10, lookback_days: 90 })
      )
    })
  })
})
