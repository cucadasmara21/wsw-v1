import React, { useState } from 'react'
import { fetchApiJson } from '../lib/api'
import StatusCard from '../components/StatusCard'

interface MarketIndicators {
  sma20: number | null
  rsi14: number | null
  volatility: number | null
  drawdown: number | null
  returns_1: number | null
  returns_n: number | null
}

interface MarketRiskComponents {
  distance_from_sma: number | null
  rsi: number | null
  volatility: number | null
  drawdown: number | null
  momentum: number | null
}

interface MarketRisk {
  score_total_0_100: number
  components: MarketRiskComponents
}

interface MarketSnapshotResponse {
  symbol: string
  timeframe: string
  last_price: number
  timestamp: string
  indicators: MarketIndicators
  risk: MarketRisk
}

export default function MarketPage() {
  const [symbol, setSymbol] = useState('TSLA')
  const [interval, setInterval] = useState('1d')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [snapshot, setSnapshot] = useState<MarketSnapshotResponse | null>(null)

  const handleLoadSnapshot = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchApiJson<MarketSnapshotResponse>(
        `/market/snapshot?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&persist=true`
      )
      setSnapshot(data)
    } catch (e: any) {
      setError(e.message || 'Failed to load snapshot')
      setSnapshot(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2>Market Snapshot</h2>

      <StatusCard title="Load Market Data">
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', marginBottom: 12 }}>
          <div>
            <label>
              Symbol:
              <input
                type="text"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                style={{ marginLeft: 8, padding: 4 }}
              />
            </label>
          </div>
          <div>
            <label>
              Interval:
              <select
                value={interval}
                onChange={(e) => setInterval(e.target.value)}
                style={{ marginLeft: 8, padding: 4 }}
              >
                <option>1m</option>
                <option>5m</option>
                <option>15m</option>
                <option>1h</option>
                <option>1d</option>
                <option>1wk</option>
              </select>
            </label>
          </div>
          <button
            onClick={handleLoadSnapshot}
            disabled={loading}
            style={{ padding: '8px 16px' }}
          >
            {loading ? 'Loading...' : 'Load Snapshot'}
          </button>
        </div>

        {error && <div style={{ color: 'red', marginBottom: 12 }}>Error: {error}</div>}
      </StatusCard>

      {snapshot && (
        <>
          <StatusCard title="Price & Indicators">
            <div style={{ display: 'flex', gap: 24 }}>
              <div>
                <h4>Last Price</h4>
                <div style={{ fontSize: 24, fontWeight: 600 }}>
                  ${snapshot.last_price.toFixed(2)}
                </div>
              </div>
              <div>
                <h4>SMA20</h4>
                <div>{snapshot.indicators.sma20?.toFixed(2) ?? 'N/A'}</div>
              </div>
              <div>
                <h4>RSI14</h4>
                <div>{snapshot.indicators.rsi14?.toFixed(2) ?? 'N/A'}</div>
              </div>
              <div>
                <h4>Volatility</h4>
                <div>{snapshot.indicators.volatility ? (snapshot.indicators.volatility * 100).toFixed(2) + '%' : 'N/A'}</div>
              </div>
              <div>
                <h4>Max Drawdown</h4>
                <div>{snapshot.indicators.drawdown ? (snapshot.indicators.drawdown * 100).toFixed(2) + '%' : 'N/A'}</div>
              </div>
            </div>
          </StatusCard>

          <StatusCard title="Risk Score">
            <div style={{ display: 'flex', gap: 24, alignItems: 'center' }}>
              <div>
                <h3>Risk Score: {snapshot.risk.score_total_0_100.toFixed(1)} / 100</h3>
                <div style={{
                  width: 200,
                  height: 30,
                  background: '#e0e0e0',
                  borderRadius: 4,
                  overflow: 'hidden'
                }}>
                  <div style={{
                    width: `${snapshot.risk.score_total_0_100}%`,
                    height: '100%',
                    background: snapshot.risk.score_total_0_100 > 70 ? '#d32f2f' : snapshot.risk.score_total_0_100 > 40 ? '#f57c00' : '#388e3c',
                    transition: 'width 0.3s'
                  }} />
                </div>
              </div>
              <div>
                <h4>Risk Components:</h4>
                <ul>
                  {Object.entries(snapshot.risk.components).map(([key, val]) =>
                    val !== null && (
                      <li key={key}>
                        {key}: {typeof val === 'number' ? val.toFixed(2) : val}
                      </li>
                    )
                  )}
                </ul>
              </div>
            </div>
          </StatusCard>

          <StatusCard title="Raw Snapshot">
            <pre style={{ maxHeight: 300, overflow: 'auto', fontSize: 12 }}>
              {JSON.stringify(snapshot, null, 2)}
            </pre>
          </StatusCard>
        </>
      )}
    </div>
  )
}
