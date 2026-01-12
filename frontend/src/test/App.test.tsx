/**
 * Smoke test: App component renders without crashing
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from '../App'

// Mock API calls
vi.mock('../lib/api', () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue([])
  }
}))

describe('App', () => {
  it('renders without crashing', () => {
    render(<App />)
    expect(screen.getByText(/WallStreetWar/i)).toBeInTheDocument()
  })

  it('renders navigation links', () => {
    render(<App />)
    // Check sidebar navigation
    expect(screen.getByText(/Overview/i)).toBeInTheDocument()
    expect(screen.getByText(/Universe/i)).toBeInTheDocument()
    expect(screen.getByText(/Health/i)).toBeInTheDocument()
  })
})
