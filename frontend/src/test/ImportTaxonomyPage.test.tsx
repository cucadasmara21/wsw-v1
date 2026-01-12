import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ImportTaxonomyPage } from '../pages/ImportTaxonomyPage'

// Mock the client
vi.mock('../api/client', () => ({
  importTaxonomy: vi.fn(),
  exportTaxonomy: vi.fn(),
}))
import * as clientModule from '../api/client'
const { importTaxonomy, exportTaxonomy } = vi.mocked(clientModule)

describe('ImportTaxonomyPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the import form', () => {
    const { container } = render(<ImportTaxonomyPage />)
    
    const heading = container.querySelector('h1')
    expect(heading).toBeDefined()
    expect(heading?.textContent).toContain('Import Taxonomy')
  })

  it('renders without crashing', () => {
    const { container } = render(<ImportTaxonomyPage />)
    expect(container).toBeDefined()
    expect(container.innerHTML.length).toBeGreaterThan(0)
  })

  it('has textarea and buttons', () => {
    const { container } = render(<ImportTaxonomyPage />)
    const textareas = container.querySelectorAll('textarea')
    expect(textareas.length).toBeGreaterThan(0)

    const buttons = container.querySelectorAll('button')
    expect(buttons.length).toBeGreaterThanOrEqual(2)
  })

  it('triggers export and download', async () => {
    const user = userEvent.setup()

    exportTaxonomy.mockResolvedValue({
      items: [
        {
          group: { name: 'G', code: 'G' },
          subgroups: [],
        },
      ],
      count: 1,
    })

    const createObjectUrl = vi.fn(() => 'blob:mock')
    const revokeObjectUrl = vi.fn()
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    vi.spyOn(URL, 'createObjectURL').mockImplementation(createObjectUrl)
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(revokeObjectUrl)

    render(<ImportTaxonomyPage />)

    const exportButton = screen.getByRole('button', { name: /Export/i })
    await user.click(exportButton)

    expect(exportTaxonomy).toHaveBeenCalledTimes(1)
    expect(createObjectUrl).toHaveBeenCalled()
    expect(clickSpy).toHaveBeenCalled()
  })

  it('loads sample Group 1 JSON when button is clicked', async () => {
    const user = userEvent.setup()
    
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          items: [
            { type: 'group', name: 'Test Group', code: 'TG' },
            { type: 'asset', symbol: 'TEST', name: 'Test Asset' }
          ]
        }),
      } as Response)
    )

    render(<ImportTaxonomyPage />)

    const loadButton = screen.getByRole('button', { name: /Load Sample Group 1/i })
    await user.click(loadButton)

    expect(global.fetch).toHaveBeenCalledWith('/samples/group1.json')
    
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement
    expect(textarea.value).toContain('Test Group')
    expect(textarea.value).toContain('Test Asset')
  })
})
