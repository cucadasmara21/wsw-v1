import { Link, Outlet, useLocation } from 'react-router-dom'
import './Layout.css'

export function Layout() {
  const location = useLocation()
  
  const isActive = (path: string) => {
    return location.pathname === path ? 'active' : ''
  }
  
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h2>WallStreetWar</h2>
        </div>
        <nav className="sidebar-nav">
          <Link to="/" className={isActive('/')}>
            📊 Overview
          </Link>
          <Link to="/universe" className={isActive('/universe')}>
            🌍 Universe
          </Link>
          <Link to="/health" className={isActive('/health')}>
            ❤️ Health
          </Link>
            <Link to="/metrics" className={isActive('/metrics')}>
              📈 Metrics
            </Link>
            <Link to="/alerts" className={isActive('/alerts')}>
              🔔 Alerts
            </Link>
            <Link to="/import-taxonomy" className={isActive('/import-taxonomy')}>
              📦 Import Taxonomy
            </Link>
        </nav>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  )
}
