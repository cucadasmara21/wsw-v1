import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { OverviewPage } from '../pages/OverviewPage'

// Mock API calls
vi.mock('../lib/api', () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue([])
  }
}))

describe('OverviewPage', () => {
  it('renders overview title', () => {
    render(
      <BrowserRouter>
        <OverviewPage />
      </BrowserRouter>
    )
    
    expect(screen.getByText('Overview')).toBeDefined()
  })
  
  it('renders stat cards', () => {
    render(
      <BrowserRouter>
        <OverviewPage />
      </BrowserRouter>
    )
    
    expect(screen.getByText('Total Assets')).toBeDefined()
    expect(screen.getByText('Asset Groups')).toBeDefined()
  })
})
