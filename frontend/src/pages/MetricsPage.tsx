import { useState, useEffect } from 'react'
import { typedGet, typedPost } from '../api/client'
import type { MetricsSnapshot, Asset } from '../api/types'
import '../components/Layout.css'

export function MetricsPage() {
  const [assets, setAssets] = useState<Asset[]>([])
  const [selectedAssetId, setSelectedAssetId] = useState<number | null>(null)
  const [metrics, setMetrics] = useState<MetricsSnapshot | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')

  // Load available assets
  useEffect(() => {
    const loadAssets = async () => {
      try {
        const data = await typedGet<Asset[]>('/assets')
        setAssets(data || [])
      } catch (err) {
        console.error('Failed to load assets:', err)
      }
    }
    loadAssets()
  }, [])

  // Load metrics when asset is selected
  useEffect(() => {
    if (!selectedAssetId) {
      setMetrics(null)
      return
    }

    const loadMetrics = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await typedGet<MetricsSnapshot>(
          `/metrics/${selectedAssetId}/metrics`
        )
        setMetrics(data)
      } catch (err: any) {
        if (err.message.includes('401')) {
          setError('Unauthorized: Please log in')
        } else if (err.message.includes('403')) {
          setError('Access denied: Insufficient permissions')
        } else if (err.message.includes('404')) {
          setError('Metrics not available for this asset. Try recomputing.')
        } else {
          setError(`Failed to load metrics: ${err.message}`)
        }
      } finally {
        setLoading(false)
      }
    }

    loadMetrics()
  }, [selectedAssetId])

  const handleRecompute = async () => {
    if (!selectedAssetId) return

    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const data = await typedPost<void, MetricsSnapshot>(
        `/metrics/${selectedAssetId}/metrics/recompute`,
        {}
      )
      setMetrics(data)
      setMessage('Metrics recomputed successfully')
      setTimeout(() => setMessage(null), 3000)
    } catch (err: any) {
      if (err.message.includes('403')) {
        setError('You do not have permission to recompute metrics')
      } else if (err.message.includes('429')) {
        setError('Too many requests. Please wait before trying again.')
      } else if (err.message.includes('503')) {
        setError('Service temporarily unavailable. Try again later.')
      } else {
        setError(`Failed to recompute metrics: ${err.message}`)
      }
    } finally {
      setLoading(false)
    }
  }

  const filteredAssets = assets.filter(
    (asset) =>
      asset.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
      asset.name?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <div className="container">
      <h1>Metrics</h1>

      {/* Asset Selector */}
      <div className="card" style={{ marginBottom: '20px' }}>
        <h2>Select Asset</h2>
        <input
          type="text"
          placeholder="Search by symbol or name..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{
            width: '100%',
            padding: '8px',
            marginBottom: '10px',
            borderRadius: '4px',
            border: '1px solid #ddd',
            boxSizing: 'border-box',
          }}
        />
        <select
          value={selectedAssetId || ''}
          onChange={(e) => setSelectedAssetId(e.target.value ? parseInt(e.target.value) : null)}
          style={{
            width: '100%',
            padding: '8px',
            borderRadius: '4px',
            border: '1px solid #ddd',
            boxSizing: 'border-box',
          }}
        >
          <option value="">Choose an asset...</option>
          {filteredAssets.map((asset) => (
            <option key={asset.id} value={asset.id}>
              {asset.symbol} - {asset.name}
            </option>
          ))}
        </select>
      </div>

      {/* Messages */}
      {error && (
        <div
          style={{
            padding: '12px',
            marginBottom: '20px',
            backgroundColor: '#fee',
            border: '1px solid #f88',
            borderRadius: '4px',
            color: '#c33',
          }}
        >
          {error}
        </div>
      )}
      {message && (
        <div
          style={{
            padding: '12px',
            marginBottom: '20px',
            backgroundColor: '#efe',
            border: '1px solid #8f8',
            borderRadius: '4px',
            color: '#3c3',
          }}
        >
          {message}
        </div>
      )}

      {/* Metrics Display */}
      {selectedAssetId && (
        <>
          {loading && <p>Loading metrics...</p>}

          {metrics && !loading && (
            <div className="card">
              <h2>Metrics Snapshot</h2>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                  gap: '15px',
                  marginBottom: '20px',
                }}
              >
                {/* Timestamp */}
                <div style={{ padding: '10px', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
                  <strong>As Of</strong>
                  <p style={{ margin: '5px 0 0 0' }}>
                    {new Date(metrics.as_of).toLocaleString()}
                  </p>
                </div>

                {/* Metrics Cards */}
                {metrics.metrics.sma20 !== undefined && (
                  <div style={{ padding: '10px', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
                    <strong>SMA20</strong>
                    <p style={{ margin: '5px 0 0 0', fontSize: '1.2em' }}>
                      {metrics.metrics.sma20.toFixed(2)}
                    </p>
                  </div>
                )}

                {metrics.metrics.rsi14 !== undefined && (
                  <div style={{ padding: '10px', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
                    <strong>RSI14</strong>
                    <p style={{ margin: '5px 0 0 0', fontSize: '1.2em' }}>
                      {metrics.metrics.rsi14.toFixed(1)}
                    </p>
                  </div>
                )}

                {metrics.metrics.volatility !== undefined && (
                  <div style={{ padding: '10px', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
                    <strong>Volatility</strong>
                    <p style={{ margin: '5px 0 0 0', fontSize: '1.2em' }}>
                      {(metrics.metrics.volatility * 100).toFixed(2)}%
                    </p>
                  </div>
                )}

                {metrics.metrics.max_drawdown !== undefined && (
                  <div style={{ padding: '10px', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
                    <strong>Max Drawdown</strong>
                    <p style={{ margin: '5px 0 0 0', fontSize: '1.2em' }}>
                      {(metrics.metrics.max_drawdown * 100).toFixed(2)}%
                    </p>
                  </div>
                )}

                {metrics.metrics.momentum !== undefined && (
                  <div style={{ padding: '10px', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
                    <strong>Momentum</strong>
                    <p style={{ margin: '5px 0 0 0', fontSize: '1.2em' }}>
                      {(metrics.metrics.momentum * 100).toFixed(2)}%
                    </p>
                  </div>
                )}

                {metrics.metrics.last_price !== undefined && (
                  <div style={{ padding: '10px', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
                    <strong>Last Price</strong>
                    <p style={{ margin: '5px 0 0 0', fontSize: '1.2em' }}>
                      {metrics.metrics.last_price.toFixed(2)}
                    </p>
                  </div>
                )}
              </div>

              {/* Data Quality */}
              {metrics.quality && (
                <div style={{ marginBottom: '20px', padding: '10px', backgroundColor: '#f9f9f9', borderRadius: '4px' }}>
                  <strong>Data Quality</strong>
                  <p style={{ margin: '5px 0 0 0', fontSize: '0.9em' }}>
                    Bars: {metrics.quality.bars_count} | Low Data: {metrics.quality.low_data ? 'Yes' : 'No'}
                  </p>
                </div>
              )}

              {/* Recompute Button */}
              <button
                onClick={handleRecompute}
                disabled={loading}
                style={{
                  padding: '10px 20px',
                  backgroundColor: '#007bff',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  opacity: loading ? 0.6 : 1,
                }}
              >
                {loading ? 'Recomputing...' : 'Recompute Metrics'}
              </button>
            </div>
          )}

          {!loading && !metrics && !error && (
            <div className="card">
              <p style={{ color: '#666' }}>No metrics available. Click "Recompute Metrics" to generate them.</p>
              <button
                onClick={handleRecompute}
                style={{
                  padding: '10px 20px',
                  backgroundColor: '#007bff',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                Recompute Metrics
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
