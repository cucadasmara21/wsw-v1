import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import MarketPage from './MarketPage'

// Mock fetchApiJson
vi.mock('../lib/api', () => ({
  fetchApiJson: vi.fn(() => Promise.resolve({
    symbol: 'TSLA',
    timeframe: '1d',
    last_price: 245.5,
    timestamp: '2025-01-11T12:00:00',
    indicators: {
      sma20: 240.0,
      rsi14: 55.5,
      volatility: 0.025,
      drawdown: 0.15,
      returns_1: 0.005,
      returns_n: 0.08
    },
    risk: {
      score_total_0_100: 45.2,
      components: {
        distance_from_sma: 2.3,
        rsi: 0.0,
        volatility: 5.0,
        drawdown: 10.0,
        momentum: 0.0
      }
    }
  }))
}))

describe('MarketPage', () => {
  it('should render without crashing', () => {
    render(<MarketPage />)
    expect(screen.getByText('Market Snapshot')).toBeInTheDocument()
    expect(screen.getByText('Load Snapshot')).toBeInTheDocument()
  })

  it('should display snapshot data after loading', async () => {
    render(<MarketPage />)
    const button = screen.getByText('Load Snapshot')
    button.click()
    
    // Wait for async operations
    await new Promise(r => setTimeout(r, 100))
    
    expect(screen.getByText(/\$245\.50/)).toBeInTheDocument()
  })
})
