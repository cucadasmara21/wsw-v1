/**
 * Smoke test: App component renders without crashing
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from '../App'

describe('App', () => {
  it('renders without crashing', () => {
    render(<App />)
    expect(screen.getByText(/WallStreetWar/i)).toBeInTheDocument()
  })

  it('renders navigation links', () => {
    render(<App />)
    // Check that navigation exists (links may appear multiple times in page)
    const dashboardLinks = screen.getAllByText(/Dashboard/i)
    expect(dashboardLinks.length).toBeGreaterThan(0)
    
    const assetsLinks = screen.getAllByText(/Assets/i)
    expect(assetsLinks.length).toBeGreaterThan(0)
    
    const scenariosLinks = screen.getAllByText(/Scenarios/i)
    expect(scenariosLinks.length).toBeGreaterThan(0)
  })
})
