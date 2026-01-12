import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { apiClient } from '../lib/api'
import { getLatestMetrics, recomputeMetrics } from '../api/client'
import type { AssetDetail, MarketSnapshot, MetricSnapshotOut } from '../api/types'

export function AssetDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [asset, setAsset] = useState<AssetDetail | null>(null)
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [marketError, setMarketError] = useState<string | null>(null)
  
  // Metrics state
  const [metricsData, setMetricsData] = useState<MetricSnapshotOut | null>(null)
  const [metricsLoading, setMetricsLoading] = useState(false)
  const [metricsError, setMetricsError] = useState<string | null>(null)
  const [recomputeLoading, setRecomputeLoading] = useState(false)
  const [recomputeMessage, setRecomputeMessage] = useState<string | null>(null)
  
  useEffect(() => {
    async function loadAsset() {
      if (!id) return
      
      try {
        const data = await apiClient.get<AssetDetail>(`/api/assets/${id}`)
        setAsset(data)
        
        // Try to load market snapshot
        try {
          const market = await apiClient.get<MarketSnapshot>(`/api/market/snapshot?symbol=${data.symbol}`)
          setSnapshot(market)
        } catch (err: any) {
          if (err?.error?.code === 'dependency_missing') {
            setMarketError('Market data requires yfinance (install requirements-optional.txt)')
          } else {
            setMarketError('Market data unavailable')
          }
        }
      } catch (err) {
        console.error('Failed to load asset:', err)
      } finally {
        setLoading(false)
      }
    }
    
    loadAsset()
  }, [id])
  
  // Load latest metrics
  useEffect(() => {
    async function loadMetrics() {
      if (!id) return
      setMetricsLoading(true)
      setMetricsError(null)
      try {
        const data = await getLatestMetrics(Number(id))
        setMetricsData(data)
      } catch (err: any) {
        const errorMsg = err.message || String(err)
        if (errorMsg.includes('503')) {
          setMetricsError('Metrics temporarily unavailable (provider disabled/quota).')
        } else if (errorMsg.includes('404')) {
          setMetricsError('No metrics available yet. Click Recompute to generate.')
        } else {
          setMetricsError('Failed to load metrics.')
        }
      } finally {
        setMetricsLoading(false)
      }
    }
    
    if (id) {
      loadMetrics()
    }
  }, [id])
  
  const handleRecompute = async () => {
    if (!id) return
    setRecomputeLoading(true)
    setRecomputeMessage(null)
    setMetricsError(null)
    try {
      const data = await recomputeMetrics(Number(id))
      setMetricsData(data)
      setRecomputeMessage('Metrics recomputed successfully!')
      setTimeout(() => setRecomputeMessage(null), 3000)
    } catch (err: any) {
      const errorMsg = err.message || String(err)
      if (errorMsg.includes('503')) {
        setMetricsError('Service temporarily unavailable. Try again later.')
      } else {
        setMetricsError('Failed to recompute metrics.')
      }
    } finally {
      setRecomputeLoading(false)
    }
  }
  
  const getScoreBadgeColor = (score: number) => {
    if (score >= 70) return '#dc2626' // red
    if (score >= 40) return '#f59e0b' // amber
    return '#16a34a' // green
  }
  
  if (loading) {
    return <div style={{ padding: '2rem' }}>Loading asset...</div>
  }
  
  if (!asset) {
    return (
      <div style={{ padding: '2rem' }}>
        <h1>Asset not found</h1>
        <button onClick={() => navigate('/universe')}>← Back to Universe</button>
      </div>
    )
  }
  
  return (
    <div style={{ padding: '2rem', maxWidth: '1200px' }}>
      <button 
        onClick={() => navigate('/universe')}
        style={{ 
          marginBottom: '1rem',
          padding: '0.5rem 1rem',
          background: '#e2e8f0',
          border: 'none',
          borderRadius: '6px',
          cursor: 'pointer'
        }}
      >
        ← Back to Universe
      </button>
      
      <div style={{ background: 'white', padding: '2rem', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', marginBottom: '1.5rem' }}>
        <h1 style={{ marginTop: 0 }}>{asset.symbol}</h1>
        <p style={{ fontSize: '1.25rem', color: '#64748b' }}>{asset.name}</p>
        
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginTop: '1.5rem' }}>
          <div>
            <div style={{ color: '#64748b', fontSize: '0.875rem' }}>Sector</div>
            <div style={{ fontWeight: '500' }}>{asset.sector || 'N/A'}</div>
          </div>
          <div>
            <div style={{ color: '#64748b', fontSize: '0.875rem' }}>Exchange</div>
            <div style={{ fontWeight: '500' }}>{asset.exchange || 'N/A'}</div>
          </div>
          <div>
            <div style={{ color: '#64748b', fontSize: '0.875rem' }}>Country</div>
            <div style={{ fontWeight: '500' }}>{asset.country || 'N/A'}</div>
          </div>
        </div>
        
        {asset.group_name && (
          <div style={{ marginTop: '1.5rem', padding: '1rem', background: '#f8fafc', borderRadius: '6px' }}>
            <div style={{ color: '#64748b', fontSize: '0.875rem' }}>Category Hierarchy</div>
            <div style={{ fontWeight: '500', marginTop: '0.5rem' }}>
              {asset.group_name} → {asset.subgroup_name} → {asset.category_name}
            </div>
          </div>
        )}
      </div>
      
      {/* Market Data */}
      <div style={{ background: 'white', padding: '2rem', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', marginBottom: '1.5rem' }}>
        <h2 style={{ marginTop: 0 }}>Market Data & Indicators</h2>
        
        {marketError ? (
          <div style={{ padding: '2rem', background: '#fef3c7', borderRadius: '6px', color: '#92400e' }}>
            ℹ️ {marketError}
            <div style={{ marginTop: '1rem', fontSize: '0.875rem' }}>
              Coming soon: Live market data and risk indicators
            </div>
          </div>
        ) : snapshot ? (
          <div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '1rem' }}>
              <div>
                <div style={{ color: '#64748b', fontSize: '0.875rem' }}>Last Price</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>${snapshot.last_price?.toFixed(2) ?? 'N/A'}</div>
              </div>
              <div>
                <div style={{ color: '#64748b', fontSize: '0.875rem' }}>Change 24h</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: (snapshot.change_24h ?? 0) >= 0 ? '#10b981' : '#ef4444' }}>
                  {snapshot.change_24h ? `${snapshot.change_24h >= 0 ? '+' : ''}${snapshot.change_24h.toFixed(2)}%` : 'N/A'}
                </div>
              </div>
              <div>
                <div style={{ color: '#64748b', fontSize: '0.875rem' }}>Volume</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>
                  {snapshot.volume ? `${(snapshot.volume / 1e6).toFixed(2)}M` : 'N/A'}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div style={{ color: '#64748b' }}>Loading market data...</div>
        )}
      </div>
      
      {/* Latest Metrics Panel */}
      <div style={{ background: 'white', padding: '2rem', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <h2 style={{ margin: 0 }}>Latest Metrics</h2>
          <button
            onClick={handleRecompute}
            disabled={recomputeLoading}
            style={{
              padding: '0.5rem 1rem',
              background: recomputeLoading ? '#cbd5e1' : '#3b82f6',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: recomputeLoading ? 'not-allowed' : 'pointer',
              fontWeight: '500'
            }}
          >
            {recomputeLoading ? 'Recomputing...' : 'Recompute'}
          </button>
        </div>
        
        {recomputeMessage && (
          <div style={{ padding: '0.75rem', marginBottom: '1rem', background: '#d1fae5', color: '#065f46', borderRadius: '6px', fontSize: '0.875rem' }}>
            ✓ {recomputeMessage}
          </div>
        )}
        
        {metricsError && (
          <div style={{ padding: '1rem', background: '#fee2e2', color: '#991b1b', borderRadius: '6px' }}>
            {metricsError}
          </div>
        )}
        
        {metricsLoading && !metricsError && (
          <div style={{ color: '#64748b' }}>Loading metrics...</div>
        )}
        
        {metricsData && !metricsLoading && !metricsError && (
          <div>
            <div style={{ 
              display: 'inline-block',
              padding: '0.75rem 1.5rem',
              background: getScoreBadgeColor(metricsData.score * 100),
              color: 'white',
              borderRadius: '8px',
              fontSize: '1.5rem',
              fontWeight: 'bold',
              marginBottom: '1.5rem'
            }}>
              Score: {(metricsData.score * 100).toFixed(1)}
            </div>
            
            <div style={{ fontSize: '0.875rem', color: '#64748b', marginBottom: '1rem' }}>
              As of: {new Date(metricsData.as_of).toLocaleString()}
            </div>
            
            {/* Calculated Metrics Grid */}
            {metricsData.metrics && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
                {metricsData.metrics.sma_20 !== undefined && (
                  <div style={{ padding: '0.75rem', background: '#f8fafc', borderRadius: '6px' }}>
                    <div style={{ color: '#64748b', fontSize: '0.75rem', marginBottom: '0.25rem' }}>SMA(20)</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 'bold' }}>
                      ${metricsData.metrics.sma_20.toFixed(2)}
                    </div>
                  </div>
                )}
                {metricsData.metrics.rsi_14 !== undefined && (
                  <div style={{ padding: '0.75rem', background: '#f8fafc', borderRadius: '6px' }}>
                    <div style={{ color: '#64748b', fontSize: '0.75rem', marginBottom: '0.25rem' }}>RSI(14)</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 'bold' }}>
                      {metricsData.metrics.rsi_14.toFixed(1)}
                    </div>
                  </div>
                )}
                {metricsData.metrics.volatility_20d !== undefined && (
                  <div style={{ padding: '0.75rem', background: '#f8fafc', borderRadius: '6px' }}>
                    <div style={{ color: '#64748b', fontSize: '0.75rem', marginBottom: '0.25rem' }}>Volatility(20d)</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 'bold' }}>
                      {(metricsData.metrics.volatility_20d * 100).toFixed(2)}%
                    </div>
                  </div>
                )}
              </div>
            )}
            
            {metricsData.explain?.items && metricsData.explain.items.length > 0 ? (
              <div>
                <h3 style={{ fontSize: '1rem', marginBottom: '0.75rem' }}>Top 3 Drivers</h3>
                <div style={{ display: 'grid', gap: '0.75rem' }}>
                  {metricsData.explain.items
                    .sort((a, b) => b.contribution - a.contribution)
                    .slice(0, 3)
                    .map((item, idx) => (
                      <div key={idx} style={{ padding: '0.75rem', background: '#f8fafc', borderRadius: '6px', display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ fontWeight: '500' }}>{item.metric_id}</span>
                        <span style={{ color: '#64748b' }}>
                          {(item.contribution * 100).toFixed(2)}% (raw: {item.raw_value.toFixed(2)})
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            ) : (
              <div style={{ color: '#64748b', fontStyle: 'italic' }}>No drivers available</div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
