/**
 * Smoke test: App component renders without crashing
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from '../App'

// Mock API calls
vi.mock('../lib/api', () => ({
  apiClient: {
    get: vi.fn((path?: string) =>
      path && typeof path === 'string' && path.includes('/universe/tree')
        ? Promise.resolve({ groups: [] })
        : Promise.resolve([])
    ),
  },
}))

describe('App', () => {
  it('renders without crashing', () => {
    render(<App />)
    expect(screen.getByText(/WallStreetWar/i)).toBeInTheDocument()
  })

  it('renders navigation links', () => {
    render(<App />)
    // Check sidebar navigation
    expect(screen.getByRole('link', { name: /Overview/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Universe/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Health/i })).toBeInTheDocument()
  })
})
