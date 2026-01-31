interface UniverseFiltersProps {
  riskMin: number
  shockMin: number
  trendFilter: Set<number>
  onRiskMinChange: (value: number) => void
  onShockMinChange: (value: number) => void
  onTrendToggle: (trend: number) => void
}

export function UniverseFilters({
  riskMin,
  shockMin,
  trendFilter,
  onRiskMinChange,
  onShockMinChange,
  onTrendToggle
}: UniverseFiltersProps) {
  const trendLabels = ['Flat', 'Bull', 'Bear']

  return (
    <div style={{
      display: 'flex',
      gap: '1.5rem',
      alignItems: 'center',
      padding: '0.5rem 1rem',
      background: 'rgba(0, 0, 0, 0.3)',
      borderRadius: '4px',
      border: '1px solid rgba(255, 255, 255, 0.1)'
    }}>
      <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.875rem', color: '#fff' }}>
        <span style={{ minWidth: '60px' }}>Risk:</span>
        <input
          type="range"
          min="0"
          max="100"
          step="1"
          value={riskMin * 100}
          onChange={(e) => onRiskMinChange(parseFloat(e.target.value) / 100)}
          style={{ width: '100px' }}
        />
        <span style={{ minWidth: '40px', color: '#0f0' }}>{(riskMin * 100).toFixed(0)}%</span>
      </label>

      <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.875rem', color: '#fff' }}>
        <span style={{ minWidth: '60px' }}>Shock:</span>
        <input
          type="range"
          min="0"
          max="100"
          step="1"
          value={shockMin * 100}
          onChange={(e) => onShockMinChange(parseFloat(e.target.value) / 100)}
          style={{ width: '100px' }}
        />
        <span style={{ minWidth: '40px', color: '#f00' }}>{(shockMin * 100).toFixed(0)}%</span>
      </label>

      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', fontSize: '0.875rem' }}>
        <span style={{ color: '#888' }}>Trend:</span>
        {[0, 1, 2].map(trend => (
          <label
            key={trend}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.25rem',
              cursor: 'pointer',
              padding: '0.25rem 0.5rem',
              background: trendFilter.has(trend) ? 'rgba(0, 255, 255, 0.2)' : 'rgba(255, 255, 255, 0.05)',
              borderRadius: '4px',
              border: `1px solid ${trendFilter.has(trend) ? '#0ff' : 'rgba(255, 255, 255, 0.2)'}`
            }}
          >
            <input
              type="checkbox"
              checked={trendFilter.has(trend)}
              onChange={() => onTrendToggle(trend)}
              style={{ cursor: 'pointer' }}
            />
            <span style={{
              color: trend === 0 ? '#fff' : trend === 1 ? '#0ff' : '#f0f',
              fontSize: '0.75rem'
            }}>
              {trendLabels[trend]}
            </span>
          </label>
        ))}
      </div>
    </div>
  )
}
