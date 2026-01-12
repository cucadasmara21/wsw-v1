import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from '../components/Layout'

describe('Layout', () => {
  it('renders sidebar navigation', () => {
    render(
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<div>Test</div>} />
          </Route>
        </Routes>
      </BrowserRouter>
    )
    
    expect(screen.getByText('WallStreetWar')).toBeDefined()
    expect(screen.getByText(/Overview/)).toBeDefined()
    expect(screen.getByText(/Universe/)).toBeDefined()
    expect(screen.getByText(/Health/)).toBeDefined()
  })
})
