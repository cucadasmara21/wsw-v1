import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiClient } from '../lib/api'
import { getLeaderboard, listAlerts } from '../api/client'
import type { Asset, LeaderboardItem, AlertOut } from '../api/types'

export function OverviewPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState({
    totalAssets: 0,
    totalGroups: 0,
    loading: true
  })
  
  const [recentAssets, setRecentAssets] = useState<Asset[]>([])
  
  // Leaderboard state
  const [leaderboard, setLeaderboard] = useState<LeaderboardItem[]>([])
  const [leaderboardLoading, setLeaderboardLoading] = useState(false)
  const [leaderboardError, setLeaderboardError] = useState<string | null>(null)
  
  // Alerts state
  const [openAlerts, setOpenAlerts] = useState<any[]>([])
  const [alertsLoading, setAlertsLoading] = useState(false)
  const [alertsError, setAlertsError] = useState<string | null>(null)
  
  useEffect(() => {
    async function loadData() {
      try {
        // Load recent assets
        const assets = await apiClient.get<Asset[]>('/api/assets/?limit=5')
        setRecentAssets(assets)
        
        // Load tree to count groups
        const tree = await apiClient.get<{ groups: any[] }>('/api/universe/tree')
        
        setStats({
          totalAssets: assets.length,
          totalGroups: tree.groups.length,
          loading: false
        })
      } catch (err) {
        console.error('Failed to load overview:', err)
        setStats(prev => ({ ...prev, loading: false }))
      }
    }
    
    loadData()
  }, [])
  
  // Load leaderboard
  useEffect(() => {
    async function loadLeaderboard() {
      setLeaderboardLoading(true)
      setLeaderboardError(null)
      try {
        const data = await getLeaderboard(1, 10) // default category_id=1, limit=10
        setLeaderboard(data)
      } catch (err: any) {
        const errorMsg = err.message || String(err)
        if (errorMsg.includes('503')) {
          setLeaderboardError('Leaderboard temporarily unavailable (provider disabled/quota).')
        } else {
          setLeaderboardError('Failed to load leaderboard.')
        }
      } finally {
        setLeaderboardLoading(false)
      }
    }
    
    loadLeaderboard()
  }, [])
  
  // Load open alerts
  useEffect(() => {
    async function loadAlerts() {
      setAlertsLoading(true)
      setAlertsError(null)
      try {
        const data = await listAlerts({ active: true })
        // Limit to 5 most recent
        setOpenAlerts(data.slice(0, 5))
      } catch (err: any) {
        const errorMsg = err.message || String(err)
        if (errorMsg.includes('503')) {
          setAlertsError('Alerts temporarily unavailable (provider disabled/quota).')
        } else {
          setAlertsError('Failed to load alerts.')
        }
      } finally {
        setAlertsLoading(false)
      }
    }
    
    loadAlerts()
  }, [])
  
  return (
    <div style={{ padding: '2rem' }}>
      <h1>Overview</h1>
      
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
        <div style={{ background: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#64748b', fontSize: '0.875rem', marginBottom: '0.5rem' }}>Total Assets</div>
          <div style={{ fontSize: '2rem', fontWeight: 'bold' }}>{stats.loading ? '...' : recentAssets.length}</div>
        </div>
        
        <div style={{ background: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#64748b', fontSize: '0.875rem', marginBottom: '0.5rem' }}>Asset Groups</div>
          <div style={{ fontSize: '2rem', fontWeight: 'bold' }}>{stats.loading ? '...' : stats.totalGroups}</div>
        </div>
      </div>
      
      <div style={{ background: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
        <h2 style={{ marginTop: 0 }}>Recent Assets</h2>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
              <th style={{ textAlign: 'left', padding: '0.75rem' }}>Symbol</th>
              <th style={{ textAlign: 'left', padding: '0.75rem' }}>Name</th>
              <th style={{ textAlign: 'left', padding: '0.75rem' }}>Sector</th>
            </tr>
          </thead>
          <tbody>
            {recentAssets.map(asset => (
              <tr key={asset.id} style={{ borderBottom: '1px solid #e2e8f0' }}>
                <td style={{ padding: '0.75rem', fontWeight: '500' }}>{asset.symbol}</td>
                <td style={{ padding: '0.75rem' }}>{asset.name}</td>
                <td style={{ padding: '0.75rem' }}>{asset.sector}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      {/* Top Risk Assets Widget */}
      <div style={{ background: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', marginTop: '2rem' }}>
        <h2 style={{ marginTop: 0 }}>Top Risk Assets</h2>
        
        {leaderboardError && (
          <div style={{ padding: '1rem', background: '#fee2e2', color: '#991b1b', borderRadius: '6px' }}>
            {leaderboardError}
          </div>
        )}
        
        {leaderboardLoading && !leaderboardError && (
          <div style={{ color: '#64748b' }}>Loading leaderboard...</div>
        )}
        
        {!leaderboardLoading && !leaderboardError && leaderboard.length === 0 && (
          <div style={{ color: '#64748b', fontStyle: 'italic' }}>No assets with metrics yet.</div>
        )}
        
        {!leaderboardLoading && !leaderboardError && leaderboard.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
                <th style={{ textAlign: 'left', padding: '0.75rem', width: '60px' }}>Rank</th>
                <th style={{ textAlign: 'left', padding: '0.75rem' }}>Symbol</th>
                <th style={{ textAlign: 'left', padding: '0.75rem' }}>Name</th>
                <th style={{ textAlign: 'left', padding: '0.75rem', width: '100px' }}>Score</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.map((item, idx) => (
                <tr 
                  key={item.asset_id} 
                  style={{ 
                    borderBottom: '1px solid #e2e8f0',
                    cursor: 'pointer',
                    transition: 'background 0.2s'
                  }}
                  onClick={() => navigate(`/assets/${item.asset_id}`)}
                  onMouseEnter={(e) => e.currentTarget.style.background = '#f8fafc'}
                  onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                >
                  <td style={{ padding: '0.75rem', fontWeight: '500', color: '#64748b' }}>#{idx + 1}</td>
                  <td style={{ padding: '0.75rem', fontWeight: '500' }}>{item.symbol}</td>
                  <td style={{ padding: '0.75rem' }}>{item.name || 'N/A'}</td>
                  <td style={{ padding: '0.75rem' }}>
                    <span style={{ 
                      padding: '0.25rem 0.5rem', 
                      background: item.score >= 0.7 ? '#fee2e2' : item.score >= 0.4 ? '#fef3c7' : '#d1fae5',
                      color: item.score >= 0.7 ? '#991b1b' : item.score >= 0.4 ? '#92400e' : '#065f46',
                      borderRadius: '4px',
                      fontSize: '0.875rem',
                      fontWeight: '600'
                    }}>
                      {(item.score * 100).toFixed(1)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Open Alerts Widget */}
      <div style={{ background: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', marginTop: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 style={{ margin: 0 }}>Open Alerts</h2>
          <a 
            href="/alerts" 
            style={{ color: '#3b82f6', textDecoration: 'none', fontSize: '0.875rem' }}
          >
            View all →
          </a>
        </div>
        
        {alertsError && (
          <div style={{ padding: '1rem', background: '#fee2e2', color: '#991b1b', borderRadius: '6px' }}>
            {alertsError}
          </div>
        )}
        
        {alertsLoading && !alertsError && (
          <div style={{ color: '#64748b' }}>Loading alerts...</div>
        )}
        
        {!alertsLoading && !alertsError && openAlerts.length === 0 && (
          <div style={{ color: '#64748b', fontStyle: 'italic', padding: '1rem', textAlign: 'center' }}>No open alerts</div>
        )}
        
        {!alertsLoading && !alertsError && openAlerts.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {openAlerts.map((alert) => (
              <div 
                key={alert.id} 
                style={{ 
                  padding: '0.75rem', 
                  background: '#f8fafc', 
                  borderLeft: `4px solid ${alert.severity === 'critical' ? '#dc2626' : alert.severity === 'warning' ? '#f59e0b' : '#3b82f6'}`,
                  borderRadius: '4px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}
              >
                <div>
                  <div style={{ fontWeight: '500', fontSize: '0.875rem' }}>
                    {alert.message}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.25rem' }}>
                    Asset ID: {alert.asset_id} • {new Date(alert.triggered_at).toLocaleString()}
                  </div>
                </div>
                <span style={{ 
                  padding: '0.25rem 0.5rem',
                  background: alert.severity === 'critical' ? '#fee2e2' : alert.severity === 'warning' ? '#fef3c7' : '#dbeafe',
                  color: alert.severity === 'critical' ? '#991b1b' : alert.severity === 'warning' ? '#92400e' : '#1e40af',
                  borderRadius: '4px',
                  fontSize: '0.75rem',
                  fontWeight: '600',
                  whiteSpace: 'nowrap'
                }}>
                  {alert.severity}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
