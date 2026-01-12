import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { apiClient } from '../lib/api'
import type { AssetDetail, MarketSnapshot } from '../api/types'

export function AssetDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [asset, setAsset] = useState<AssetDetail | null>(null)
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [marketError, setMarketError] = useState<string | null>(null)
  
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
      <div style={{ background: 'white', padding: '2rem', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
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
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
              <div>
                <div style={{ color: '#64748b', fontSize: '0.875rem' }}>Last Price</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>${snapshot.last_price.toFixed(2)}</div>
              </div>
              <div>
                <div style={{ color: '#64748b', fontSize: '0.875rem' }}>SMA(20)</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>
                  {snapshot.indicators.sma20 ? `$${snapshot.indicators.sma20.toFixed(2)}` : 'N/A'}
                </div>
              </div>
              <div>
                <div style={{ color: '#64748b', fontSize: '0.875rem' }}>RSI(14)</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>
                  {snapshot.indicators.rsi14 ? snapshot.indicators.rsi14.toFixed(1) : 'N/A'}
                </div>
              </div>
            </div>
            
            <div style={{ padding: '1.5rem', background: '#f1f5f9', borderRadius: '6px' }}>
              <h3 style={{ marginTop: 0 }}>Risk Score</h3>
              <div style={{ fontSize: '2rem', fontWeight: 'bold', color: '#dc2626' }}>
                {snapshot.risk.score_total_0_100.toFixed(1)}/100
              </div>
            </div>
          </div>
        ) : (
          <div style={{ color: '#64748b' }}>Loading market data...</div>
        )}
      </div>
    </div>
  )
}
