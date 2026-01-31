import { PointData } from '../hooks/usePointPicking'

interface PointTooltipProps {
  point: PointData | null
  mouseX: number
  mouseY: number
}

export function PointTooltip({ point, mouseX, mouseY }: PointTooltipProps) {
  if (!point) return null

  const trendLabels = ['Flat', 'Bull', 'Bear', 'Reserved']
  const trendColors = ['#fff', '#0ff', '#f0f', '#888']

  return (
    <div
      style={{
        position: 'fixed',
        left: `${mouseX + 15}px`,
        top: `${mouseY + 15}px`,
        background: 'rgba(0, 0, 0, 0.9)',
        padding: '0.75rem',
        borderRadius: '4px',
        fontFamily: 'monospace',
        fontSize: '0.75rem',
        color: '#fff',
        backdropFilter: 'blur(10px)',
        pointerEvents: 'none',
        zIndex: 10000,
        border: '1px solid rgba(255, 255, 255, 0.2)',
        minWidth: '200px'
      }}
    >
      <div style={{ fontWeight: 'bold', marginBottom: '0.5rem', color: '#0ff' }}>
        {point.symbol}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.25rem', fontSize: '0.7rem' }}>
        <div>Risk:</div>
        <div style={{ color: '#0f0' }}>{(point.risk * 100).toFixed(1)}%</div>
        <div>Shock:</div>
        <div style={{ color: '#f00' }}>{(point.shock * 100).toFixed(1)}%</div>
        <div>Trend:</div>
        <div style={{ color: trendColors[point.trend] }}>
          {trendLabels[point.trend]}
        </div>
        <div>Vitality:</div>
        <div style={{ color: '#ff0' }}>{(point.vital * 100).toFixed(1)}%</div>
        <div>Macro:</div>
        <div style={{ color: '#f0f' }}>{(point.macro * 100).toFixed(1)}%</div>
      </div>
    </div>
  )
}
