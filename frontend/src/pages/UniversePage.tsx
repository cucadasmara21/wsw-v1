import { useEffect, useState, useRef, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { TitanCanvas, type TitanCanvasRef } from '../components/TitanCanvas'
import { fetchApiRaw, apiClient } from '../lib/api'
import type { Asset } from '../api/types'
import { TitanPanel } from '../components/titan/TitanPanel'
import { TitanTable } from '../components/titan/TitanTable'
import { UniverseFilters } from '../components/UniverseFilters'
import { AssetDetailPanel } from '../components/AssetDetailPanel'
import type { PointData } from '../hooks/usePointPicking'

type UniverseTreeV1 = {
  groups: Array<{
    name: string
    count: number
    subgroups: Array<{ name: string; count: number }>
  }>
}

export function UniversePage() {
  const navigate = useNavigate()
  const [tree, setTree] = useState<UniverseTreeV1 | null>(null)
  const [treeWarning, setTreeWarning] = useState<string | null>(null)
  const [assets, setAssets] = useState<Asset[]>([])
  const [selectedCategory, setSelectedCategory] = useState<number | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [pointSize, setPointSize] = useState(10.0)
  const [glowStrength, setGlowStrength] = useState(1.0)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [riskMin, setRiskMin] = useState(0)
  const [shockMin, setShockMin] = useState(0)
  const [trendFilter, setTrendFilter] = useState<Set<number>>(new Set([0, 1, 2]))
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)
  const titanCanvasRef = useRef<TitanCanvasRef>(null)

  // Memoize pollMs to prevent prop recreation on every render
  const pollMs = useMemo(() => (autoRefresh ? 2000 : 0), [autoRefresh])

  // Debug selectedSymbol changes
  useEffect(() => {
    console.debug('[UniversePage] selectedSymbol=', selectedSymbol)
  }, [selectedSymbol])

  // Handle point pick -> extract symbol -> set selectedSymbol
  const handlePick = useCallback((p: PointData | null) => {
    console.debug('[UniversePage] onPick p=', p)
    if (!p) return
    const symbol =
      (p as any).symbol ??
      (p as any).meta?.symbol ??
      (p as any).name ??
      (p as any).label ??
      null
    if (symbol) {
      setSelectedSymbol(String(symbol))
    }
  }, [])

  useEffect(() => {
    async function loadTree() {
      try {
        setTreeWarning(null)
        const path = '/universe/tree'
        const res = await fetchApiRaw(path)
        const bodyText = await res.text()
        const logPayload: any = {
          path,
          status: res.status,
          ok: res.ok,
          bodyHead: bodyText.slice(0, 200)
        }
        // #region agent log
        fetch('http://127.0.0.1:7242/ingest/2c312865-94f7-427e-905b-dc7584b4541a', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sessionId: 'debug-session',
            runId: 'run1',
            hypothesisId: 'H1',
            location: 'frontend/src/pages/UniversePage.tsx:loadTree',
            message: 'tree_fetch_result',
            data: logPayload,
            timestamp: Date.now()
          })
        }).catch(() => {})
        // #endregion agent log

        if (!res.ok) {
          console.error('Failed to load universe tree:', { status: res.status, body: bodyText })
          setTreeWarning(`HTTP ${res.status}: ${bodyText.slice(0, 120)}`)
          return
        }

        let json: UniverseTreeV1
        try {
          json = JSON.parse(bodyText) as UniverseTreeV1
        } catch (e) {
          console.error('Failed to parse universe tree JSON:', e)
          setTreeWarning('Tree parse error')
          return
        }
        setTree(json)
      } catch (err: any) {
        const msg = err?.message ?? String(err)
        console.error('Failed to load universe tree:', { message: msg, err })
        setTreeWarning(msg)
      }
    }
    loadTree()
  }, [])

  useEffect(() => {
    async function loadAssets() {
      try {
        let url = '/assets/?limit=50'
        if (selectedCategory) {
          url += `&category_id=${selectedCategory}`
        }
        if (searchQuery) {
          url += `&q=${encodeURIComponent(searchQuery)}`
        }
        const data = await apiClient.get<Asset[]>(url)
        setAssets(data)
      } catch (err) {
        console.error('Failed to load assets:', err)
      }
    }
    loadAssets()
  }, [selectedCategory, searchQuery])

  const handleRefresh = () => {
    titanCanvasRef.current?.refresh()
  }

  const onAssetClick = useCallback((symbol: string) => {
    console.debug('[UniversePage] onAssetClick symbol=', symbol)
    setSelectedSymbol(symbol)
  }, [])

  return (
    <div 
      style={{
        display: 'flex',
        height: '100vh',
        width: '100%',
        overflow: 'hidden',
        position: 'relative'
      }}
    >
      <div style={{
        width: '250px',
        background: 'var(--panel)',
        borderRight: '1px solid var(--panel-border)',
        backdropFilter: 'blur(10px)',
        overflowY: 'auto',
        padding: '1rem'
      }}>
        <h3 style={{ marginTop: 0, color: 'var(--cyan)', textShadow: 'var(--glow-cyan)' }}>Universe Tree</h3>
        {treeWarning ? (
          <div style={{ marginBottom: '0.75rem', fontSize: '0.85rem', color: 'var(--muted)' }}>
            Tree unavailable: {treeWarning}
          </div>
        ) : null}
        {tree?.groups.map(group => (
          <details key={group.name} open style={{ marginBottom: '1rem' }}>
            <summary style={{
              fontWeight: 'bold',
              cursor: 'pointer',
              padding: '0.5rem',
              background: 'rgba(6, 182, 212, 0.1)',
              borderRadius: '4px',
              color: 'var(--cyan)'
            }}>
              {group.name} <span style={{ color: 'var(--muted)', fontWeight: 400 }}>({group.count})</span>
            </summary>
            <div style={{ paddingLeft: '1rem', marginTop: '0.5rem' }}>
              {group.subgroups.map(subgroup => (
                <div key={`${group.name}:${subgroup.name}`} style={{ marginBottom: '0.5rem' }}>
                  <div style={{ padding: '0.25rem', color: 'var(--muted)' }}>
                    {subgroup.name}{' '}
                    <span style={{ color: 'var(--muted)', fontWeight: 400 }}>({subgroup.count})</span>
                  </div>
                </div>
              ))}
            </div>
          </details>
        ))}
      </div>

      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        height: '100vh'
      }}>
        <div style={{
          padding: '0.75rem 1rem',
          background: 'var(--panel)',
          borderBottom: '1px solid var(--panel-border)',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.75rem',
          backdropFilter: 'blur(10px)',
          flexShrink: 0
        }}>
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <div
              style={{
                padding: '0.5rem 1rem',
                background: 'var(--cyan)',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                fontFamily: 'monospace',
                fontSize: '0.875rem'
              }}
            >
              TITAN MODE
            </div>
            <button
              onClick={handleRefresh}
              style={{
                padding: '0.5rem 1rem',
                background: 'var(--green)',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontFamily: 'monospace',
                fontSize: '0.875rem'
              }}
            >
              REFRESH
            </button>
            <label style={{ color: 'var(--muted)', fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              Auto-refresh
            </label>
            <label style={{ color: 'var(--muted)', fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              Point Size:
              <input
                type="range"
                min="2"
                max="20"
                step="0.5"
                value={pointSize}
                onChange={(e) => setPointSize(parseFloat(e.target.value))}
                style={{ width: '100px' }}
              />
              <span style={{ color: 'var(--cyan)', minWidth: '30px' }}>{pointSize.toFixed(1)}</span>
            </label>
            <label style={{ color: 'var(--muted)', fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              Glow:
              <input
                type="range"
                min="0"
                max="2"
                step="0.1"
                value={glowStrength}
                onChange={(e) => setGlowStrength(parseFloat(e.target.value))}
                style={{ width: '100px' }}
              />
              <span style={{ color: 'var(--cyan)', minWidth: '30px' }}>{glowStrength.toFixed(1)}</span>
            </label>
          </div>
          <UniverseFilters
            riskMin={riskMin}
            shockMin={shockMin}
            trendFilter={trendFilter}
            onRiskMinChange={setRiskMin}
            onShockMinChange={setShockMin}
            onTrendToggle={(trend) => {
              setTrendFilter(prev => {
                const next = new Set(prev)
                if (next.has(trend)) {
                  next.delete(trend)
                } else {
                  next.add(trend)
                }
                return next
              })
            }}
          />
        </div>
        
        <div style={{
          flex: 1,
          position: 'relative',
          background: 'var(--bg-0)',
          width: '100%',
          height: '100%',
          overflow: 'hidden'
        }}>
          <TitanCanvas
            ref={titanCanvasRef}
            pointSize={pointSize}
            glowStrength={glowStrength}
            pollMs={pollMs}
            riskMin={riskMin}
            shockMin={shockMin}
            trendFilter={trendFilter}
            onAssetClick={onAssetClick}
            onPick={handlePick}
          />
        </div>
      </div>

      <div style={{
        width: '300px',
        background: 'var(--panel)',
        borderLeft: '1px solid var(--panel-border)',
        backdropFilter: 'blur(10px)',
        overflowY: 'auto',
        padding: '1rem',
        display: 'flex',
        flexDirection: 'column'
      }}>
        <div style={{ marginBottom: '1rem' }}>
          <input
            type="search"
            placeholder="Search assets..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: '100%',
              padding: '0.5rem',
              background: 'var(--bg-1)',
              border: '1px solid var(--panel-border)',
              borderRadius: '4px',
              color: 'var(--text)',
              fontFamily: 'monospace',
              fontSize: '0.875rem'
            }}
          />
        </div>
        <TitanPanel>
          <TitanTable headers={['Symbol', 'Name', 'Sector']}>
            {assets.map(asset => (
              <tr
                key={asset.id}
                onClick={() => navigate(`/assets/${asset.id}`)}
                style={{ cursor: 'pointer' }}
              >
                <td style={{ fontWeight: '500', color: 'var(--cyan)' }}>{asset.symbol}</td>
                <td>{asset.name}</td>
                <td style={{ color: 'var(--muted)' }}>{asset.sector}</td>
              </tr>
            ))}
          </TitanTable>
        </TitanPanel>
      </div>

        <div style={{
          position: 'absolute',
          right: 0,
          top: 0,
          height: '100%',
          width: '320px',
          zIndex: 50,
          display: selectedSymbol ? 'block' : 'none'
        }}>
          <AssetDetailPanel
            symbol={selectedSymbol}
            onClose={() => setSelectedSymbol(null)}
          />
        </div>
    </div>
  )
}
