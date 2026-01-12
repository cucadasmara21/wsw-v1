import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { ImportTaxonomyPage } from '../pages/ImportTaxonomyPage'

// Mock the client
vi.mock('../api/client', () => ({
  importTaxonomy: vi.fn(),
}))

describe('ImportTaxonomyPage', () => {
  it('renders the import form', () => {
    const { container } = render(<ImportTaxonomyPage />)
    
    // Check main heading
    const heading = container.querySelector('h1')
    expect(heading).toBeDefined()
    expect(heading?.textContent).toContain('Import Taxonomy')
  })

  it('renders without crashing', () => {
    const { container } = render(<ImportTaxonomyPage />)
    
    // Just verify it renders without errors
    expect(container).toBeDefined()
    expect(container.innerHTML.length).toBeGreaterThan(0)
  })

  it('has textarea for JSON input', () => {
    const { container } = render(<ImportTaxonomyPage />)
    
    const textareas = container.querySelectorAll('textarea')
    expect(textareas.length).toBeGreaterThan(0)
  })

  it('has import button', () => {
    const { container } = render(<ImportTaxonomyPage />)
    
    const buttons = container.querySelectorAll('button')
    expect(buttons.length).toBeGreaterThan(0)
  })
})
