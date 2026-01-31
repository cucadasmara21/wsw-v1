interface TitanKPIProps {
  value: string | number
  label: string
  trend?: string
  glowColor?: 'cyan' | 'magenta' | 'green' | 'amber'
}

export function TitanKPI({ value, label, trend, glowColor = 'cyan' }: TitanKPIProps) {
  const glowClass = `titan-kpi-value-${glowColor}`
  
  return (
    <div className="titan-kpi">
      <div className={`titan-kpi-value ${glowClass}`} style={{
        textShadow: glowColor === 'cyan' ? 'var(--glow-cyan)' :
                    glowColor === 'magenta' ? 'var(--glow-magenta)' :
                    glowColor === 'green' ? 'var(--glow-green)' :
                    'var(--glow-amber)',
        color: glowColor === 'cyan' ? 'var(--cyan)' :
               glowColor === 'magenta' ? 'var(--magenta)' :
               glowColor === 'green' ? 'var(--green)' :
               'var(--amber)'
      }}>
        {value}
      </div>
      <div className="titan-kpi-label">{label}</div>
      {trend && <div className="titan-kpi-trend">{trend}</div>}
    </div>
  )
}
