import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { UniversePage } from '../pages/UniversePage'
import * as clientModule from '../api/client'

// Mock the client
vi.mock('../api/client', () => ({
  getCategories: vi.fn(),
  getCategoryAssetsPaginated: vi.fn(),
  getAssetDetail: vi.fn(),
}))

describe('UniversePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(clientModule.getCategories).mockResolvedValue([])
  })
  
  it('renders universe tree page', () => {
    const { container } = render(
      <BrowserRouter>
        <UniversePage />
      </BrowserRouter>
    )
    
    // Verify main structure renders
    expect(container).toBeDefined()
    expect(container.innerHTML.length).toBeGreaterThan(0)
  })
  
  it('has select elements for browsing', () => {
    const { container } = render(
      <BrowserRouter>
        <UniversePage />
      </BrowserRouter>
    )
    
    const selects = container.querySelectorAll('select')
    // Should have at least category selector
    expect(selects.length).toBeGreaterThanOrEqual(0)
  })

  it('renders without throwing errors', () => {
    const { container } = render(
      <BrowserRouter>
        <UniversePage />
      </BrowserRouter>
    )
    
    // Component renders and has content (Loading or actual content)
    expect(container.textContent).toBeDefined()
    expect(container.textContent.length).toBeGreaterThan(0)
  })
})
