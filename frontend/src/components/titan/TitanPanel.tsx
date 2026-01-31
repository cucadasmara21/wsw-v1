import { ReactNode } from 'react'

interface TitanPanelProps {
  children: ReactNode
  className?: string
  style?: React.CSSProperties
}

export function TitanPanel({ children, className = '', style }: TitanPanelProps) {
  return (
    <div className={`titan-panel ${className}`} style={style}>
      {children}
    </div>
  )
}
