import { useEffect, useState, useRef } from 'react'

// Module-level cache with 10s TTL
const cache = new Map<string, { ts: number; data: any }>()
const TTL_MS = 10_000

type AssetRisk = { risk: number; shock: number; trend: 0 | 1 | 2; vital: number; macro: number }
type AssetDetail = {
  symbol: string
  name: string
  sector: string
  last: number
  change_pct: number
  sparkline: number[]
  risk: AssetRisk
  ts: number
  stale?: boolean
  build_tag?: string
}

interface AssetDetailPanelProps {
  symbol: string | null
  onClose: () => void
}

export function AssetDetailPanel({ symbol, onClose }: AssetDetailPanelProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<AssetDetail | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const reqSeqRef = useRef(0)

  useEffect(() => {
    if (!symbol) {
      setData(null)
      setLoading(false)
      setError(null)
      return
    }

    console.debug('[AssetDetailPanel] effect symbol=', symbol)
    
    // Abort previous request
    abortRef.current?.abort()

    // Check cache (10s TTL)
    const hit = cache.get(symbol)
    const now = Date.now()
    const isCacheHit = hit && now - hit.ts < TTL_MS
    console.debug('[AssetDetailPanel] cache', isCacheHit ? 'HIT' : 'MISS', symbol)
    
    if (isCacheHit) {
      // Cache hit: render instantly, no network request
      console.debug('[AssetDetailPanel] cache hit', symbol)
      setData(hit.data)
      setLoading(false)
      setError(null)
      return
    }

    // Cache miss: fetch from network
    setLoading(true)
    setError(null)
    setData(null)

    const mySeq = ++reqSeqRef.current
    const ac = new AbortController()
    abortRef.current = ac

    // Use relative path - Vite proxy handles routing to backend
    const url = `/api/asset/detail?symbol=${encodeURIComponent(symbol)}`
    
    // Dev-only instrumentation log
    if (import.meta.env.DEV) {
      console.debug('[AssetDetailPanel] url=', url)
    }
    
    fetch(url, { signal: ac.signal })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((fetchedData: AssetDetail) => {
        // Request sequence guard: ignore stale completions
        if (ac.signal.aborted) return
        if (mySeq !== reqSeqRef.current) return

        cache.set(symbol, { ts: Date.now(), data: fetchedData })
        setData(fetchedData)
        setLoading(false)
        setError(null)
      })
      .catch(err => {
        if (err?.name === 'AbortError') {
          // Request was canceled, ignore
          return
        }
        // Request sequence guard: ignore stale errors
        if (mySeq !== reqSeqRef.current) return

        console.error('[AssetDetailPanel] fetch failed:', err)
        setError(err.message || 'Failed to load asset details')
        setLoading(false)
      })

    // Cleanup: abort on unmount or symbol change
    return () => {
      ac.abort()
    }
  }, [symbol])

  const trendLabel = (trend: 0 | 1 | 2): string => {
    if (trend === 1) return '↑ Bull'
    if (trend === 2) return '↓ Bear'
    return '→ Flat'
  }

  return (
    <div
      style={{
        background: 'var(--panel)',
        borderLeft: '1px solid var(--panel-border)',
        backdropFilter: 'blur(10px)',
        overflowY: 'auto',
        padding: '1rem',
        display: 'flex',
        flexDirection: 'column',
        height: '100%'
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h3 style={{ margin: 0, color: 'var(--cyan)', fontSize: '1rem' }}>
          {symbol}
          {data?.build_tag && (
            <span style={{ marginLeft: '0.5rem', fontSize: '0.7rem', color: 'var(--muted)' }}>
              [{data.build_tag}]
            </span>
          )}
          {data?.stale && (
            <span style={{
              marginLeft: '0.5rem',
              fontSize: '0.7rem',
              padding: '0.125rem 0.375rem',
              background: 'var(--yellow)',
              color: 'black',
              borderRadius: '4px',
              fontWeight: 'bold'
            }}>
              STALE
            </span>
          )}
        </h3>
        <button
          onClick={onClose}
          style={{
            background: 'transparent',
            border: '1px solid var(--panel-border)',
            color: 'var(--text)',
            borderRadius: '4px',
            padding: '0.25rem 0.5rem',
            cursor: 'pointer',
            fontSize: '0.75rem'
          }}
        >
          ✕
        </button>
      </div>

      {loading && (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--muted)', fontSize: '0.875rem' }}>
          Loading {symbol}...
        </div>
      )}

      {error && (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--red)', fontSize: '0.875rem' }}>
          Failed to load {symbol}
        </div>
      )}

      {data && !loading && !error && (
        <>
          <div style={{ marginBottom: '1rem' }}>
            {data.name && (
              <div style={{ color: 'var(--muted)', fontSize: '0.75rem', marginBottom: '0.25rem' }}>
                {data.name}
              </div>
            )}
            {data.sector && (
              <div style={{ color: 'var(--muted)', fontSize: '0.75rem' }}>
                {data.sector}
              </div>
            )}
          </div>

          <div style={{ marginBottom: '1rem', padding: '1rem', background: 'rgba(6, 182, 212, 0.1)', borderRadius: '4px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.5rem' }}>
              <div style={{ color: 'var(--muted)' }}>Last Price</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--cyan)' }}>
                {data.last === 0.0 ? 'N/A' : `$${data.last.toFixed(2)}`}
              </div>
            </div>
            {data.change_pct !== null && data.change_pct !== 0.0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <div style={{ color: 'var(--muted)' }}>Change</div>
                <div style={{
                  color: data.change_pct >= 0 ? 'var(--green)' : 'var(--red)',
                  fontWeight: 'bold'
                }}>
                  {data.change_pct >= 0 ? '+' : ''}{data.change_pct.toFixed(2)}%
                </div>
              </div>
            )}
          </div>

          {data.sparkline && data.sparkline.length >= 2 ? (
            <div style={{ marginBottom: '1rem' }}>
              <div style={{ color: 'var(--muted)', marginBottom: '0.5rem', fontSize: '0.75rem' }}>Price History</div>
              <SparklineSVG data={data.sparkline} width={280} height={60} />
            </div>
          ) : (
            <div style={{ marginBottom: '1rem', padding: '1rem', textAlign: 'center', color: 'var(--muted)', fontSize: '0.75rem' }}>
              No sparkline
            </div>
          )}

          <div style={{ borderTop: '1px solid var(--panel-border)', paddingTop: '1rem' }}>
            <div style={{ color: 'var(--muted)', marginBottom: '0.5rem', fontSize: '0.75rem' }}>Risk Metrics</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: '0.75rem' }}>
              <div style={{ color: 'var(--muted)' }}>Risk:</div>
              <div style={{ color: 'var(--green)' }}>{(data.risk.risk * 100).toFixed(1)}%</div>
              <div style={{ color: 'var(--muted)' }}>Shock:</div>
              <div style={{ color: 'var(--red)' }}>{(data.risk.shock * 100).toFixed(1)}%</div>
              <div style={{ color: 'var(--muted)' }}>Trend:</div>
              <div style={{ color: data.risk.trend === 1 ? 'var(--green)' : data.risk.trend === 2 ? 'var(--red)' : 'var(--muted)' }}>
                {trendLabel(data.risk.trend)}
              </div>
              <div style={{ color: 'var(--muted)' }}>Vital:</div>
              <div style={{ color: 'var(--yellow)' }}>{(data.risk.vital * 100).toFixed(1)}%</div>
              <div style={{ color: 'var(--muted)' }}>Macro:</div>
              <div style={{ color: 'var(--purple)' }}>{(data.risk.macro * 100).toFixed(1)}%</div>
            </div>
          </div>

          {data.ts && (
            <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--panel-border)', fontSize: '0.7rem', color: 'var(--muted)' }}>
              Updated: {new Date(data.ts).toLocaleTimeString()}
            </div>
          )}
        </>
      )}
    </div>
  )
}

// Simple SVG polyline sparkline (no external chart lib)
function SparklineSVG({ data, width, height }: { data: number[]; width: number; height: number }) {
  if (data.length === 0) {
    return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: '0.75rem' }}>No data</div>
  }

  // Filter out null/NaN values
  const validData = data.filter((v): v is number => v !== null && !isNaN(v))
  if (validData.length === 0) {
    return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: '0.75rem' }}>No valid data</div>
  }

  // Normalize to [0..1] in Y
  const min = Math.min(...validData)
  const max = Math.max(...validData)
  const range = max - min || 1

  // Build points string for polyline
  const points = validData.map((value, i) => {
    const x = (i / (validData.length - 1)) * width
    const y = height - ((value - min) / range) * height
    return `${x},${y}`
  }).join(' ')

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <polyline
        points={points}
        fill="none"
        stroke="var(--cyan)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
