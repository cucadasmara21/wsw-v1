import { Link, Outlet, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import './Layout.css'

export function Layout() {
  const location = useLocation()
  const [apiStatus, setApiStatus] = useState<'LIVE' | 'DEGRADED' | 'OFFLINE'>('OFFLINE')
  
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch('/health')
        if (res.ok || res.status === 304) {
          const data = await res.json()
          setApiStatus(data.status === 'healthy' ? 'LIVE' : 'DEGRADED')
        } else {
          setApiStatus('DEGRADED')
        }
      } catch {
        setApiStatus('OFFLINE')
      }
    }
    
    checkHealth()
    const interval = setInterval(checkHealth, 10000)
    return () => clearInterval(interval)
  }, [])
  
  const isActive = (path: string) => {
    return location.pathname === path ? 'active' : ''
  }
  
  return (
    <div className="layout">
      <aside className="sidebar glass-sidebar">
        <div className="glass-sidebar-header">
          <h2>WallStreetWar</h2>
        </div>
        <nav className="sidebar-nav">
          <Link to="/" className={`glass-nav-link ${isActive('/')}`}>
            📊 Overview
          </Link>
          <Link to="/universe" className={`glass-nav-link ${isActive('/universe')}`}>
            🌍 Universe
          </Link>
          <Link to="/health" className={`glass-nav-link ${isActive('/health')}`}>
            ❤️ Health
          </Link>
          <Link to="/metrics" className={`glass-nav-link ${isActive('/metrics')}`}>
            📈 Metrics
          </Link>
          <Link to="/alerts" className={`glass-nav-link ${isActive('/alerts')}`}>
            🔔 Alerts
          </Link>
        </nav>
        <div style={{ padding: '1rem', borderTop: '1px solid var(--panel-border)' }}>
          <div className={`status-pill ${apiStatus.toLowerCase()}`}>
            API: {apiStatus}
          </div>
        </div>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  )
}
