import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { UniversePage } from '../pages/UniversePage'

// Mock API calls
vi.mock('../lib/api', () => ({
  apiClient: {
    get: vi.fn((path: string) => {
      if (path.includes('/universe/tree')) {
        return Promise.resolve({ groups: [] })
      }
      return Promise.resolve([])
    })
  }
}))

describe('UniversePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })
  
  it('renders universe tree header', async () => {
    render(
      <BrowserRouter>
        <UniversePage />
      </BrowserRouter>
    )
    
    await waitFor(() => {
      expect(screen.getByText('Universe Tree')).toBeDefined()
    })
  })
  
  it('renders search input', async () => {
    render(
      <BrowserRouter>
        <UniversePage />
      </BrowserRouter>
    )
    
    await waitFor(() => {
      const searchInput = screen.getByPlaceholderText('Search assets...')
      expect(searchInput).toBeDefined()
    })
  })
})
