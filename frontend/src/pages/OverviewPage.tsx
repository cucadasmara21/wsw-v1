import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiClient } from '../lib/api'
import { getLeaderboard, listAlerts } from '../api/client'
import type { Asset, LeaderboardItem, AlertOut } from '../api/types'
import { TitanPanel } from '../components/titan/TitanPanel'
import { TitanKPI } from '../components/titan/TitanKPI'
import { TitanTable } from '../components/titan/TitanTable'

export function OverviewPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState({
    totalAssets: 0,
    totalGroups: 0,
    loading: true
  })
  const [recentAssets, setRecentAssets] = useState<Asset[]>([])
  const [leaderboard, setLeaderboard] = useState<LeaderboardItem[]>([])
  const [leaderboardLoading, setLeaderboardLoading] = useState(false)
  const [leaderboardError, setLeaderboardError] = useState<string | null>(null)
  const [openAlerts, setOpenAlerts] = useState<any[]>([])
  const [alertsLoading, setAlertsLoading] = useState(false)
  const [alertsError, setAlertsError] = useState<string | null>(null)

  useEffect(() => {
    async function loadData() {
      try {
        const assets = await apiClient.get<Asset[]>('/assets/?limit=5')
        setRecentAssets(assets)
        const tree = await apiClient.get<{ groups: any[] }>('/universe/tree')
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

  useEffect(() => {
    async function loadLeaderboard() {
      setLeaderboardLoading(true)
      setLeaderboardError(null)
      try {
        const data = await getLeaderboard(1, 10)
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

  useEffect(() => {
    async function loadAlerts() {
      setAlertsLoading(true)
      setAlertsError(null)
      try {
        const data = await listAlerts({ active: true })
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
    <div style={{ padding: '2rem', position: 'relative', zIndex: 1 }}>
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{
          margin: '0 0 0.5rem 0',
          fontSize: '2.5rem',
          color: 'var(--cyan)',
          textShadow: 'var(--glow-cyan)',
          letterSpacing: '0.05em'
        }}>
          Sovereign Command Center
        </h1>
        <p style={{ color: 'var(--muted)', fontSize: '0.875rem', margin: 0 }}>
          Environment: Production • Stride: 28-byte OK • Last Refresh: {new Date().toLocaleTimeString()}
        </p>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
        gap: '1.5rem',
        marginBottom: '2rem'
      }}>
        <TitanPanel>
          <TitanKPI
            value={stats.loading ? '...' : recentAssets.length}
            label="Total Assets"
            glowColor="cyan"
          />
        </TitanPanel>
        <TitanPanel>
          <TitanKPI
            value={stats.loading ? '...' : stats.totalGroups}
            label="Asset Groups"
            glowColor="magenta"
          />
        </TitanPanel>
        <TitanPanel>
          <TitanKPI
            value={openAlerts.length}
            label="Open Alerts"
            glowColor={openAlerts.length > 0 ? 'amber' : 'green'}
          />
        </TitanPanel>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '2rem' }}>
        <TitanPanel>
          <div style={{ padding: '1.5rem' }}>
            <h2 style={{ marginTop: 0, color: 'var(--cyan)', marginBottom: '1rem' }}>Recent Assets</h2>
            <TitanTable headers={['Symbol', 'Name', 'Sector']}>
              {recentAssets.map(asset => (
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
          </div>
        </TitanPanel>

        <TitanPanel>
          <div style={{ padding: '1.5rem' }}>
            <h2 style={{ marginTop: 0, color: 'var(--cyan)', marginBottom: '1rem' }}>Top Risk Assets</h2>
            {leaderboardError && (
              <div style={{
                padding: '1rem',
                background: 'rgba(217, 70, 239, 0.2)',
                color: 'var(--magenta)',
                borderRadius: '6px',
                border: '1px solid var(--magenta)'
              }}>
                {leaderboardError}
              </div>
            )}
            {leaderboardLoading && !leaderboardError && (
              <div style={{ color: 'var(--muted)' }}>Loading leaderboard...</div>
            )}
            {!leaderboardLoading && !leaderboardError && leaderboard.length === 0 && (
              <div style={{
                padding: '2rem',
                textAlign: 'center',
                color: 'var(--muted)',
                fontStyle: 'italic',
                background: 'rgba(6, 182, 212, 0.05)',
                borderRadius: '6px',
                border: '1px dashed var(--panel-border)'
              }}>
                No assets with metrics yet.
              </div>
            )}
            {!leaderboardLoading && !leaderboardError && leaderboard.length > 0 && (
              <TitanTable headers={['Rank', 'Symbol', 'Name', 'Score']}>
                {leaderboard.map((item, idx) => (
                  <tr
                    key={item.asset_id}
                    onClick={() => navigate(`/assets/${item.asset_id}`)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td style={{ fontWeight: '500', color: 'var(--muted)' }}>#{idx + 1}</td>
                    <td style={{ fontWeight: '500', color: 'var(--cyan)' }}>{item.symbol}</td>
                    <td>{item.name || 'N/A'}</td>
                    <td>
                      <span style={{
                        padding: '0.25rem 0.5rem',
                        background: item.score >= 0.7 ? 'rgba(217, 70, 239, 0.2)' :
                                    item.score >= 0.4 ? 'rgba(245, 158, 11, 0.2)' :
                                    'rgba(16, 185, 129, 0.2)',
                        color: item.score >= 0.7 ? 'var(--magenta)' :
                               item.score >= 0.4 ? 'var(--amber)' :
                               'var(--green)',
                        borderRadius: '4px',
                        fontSize: '0.875rem',
                        fontWeight: '600'
                      }}>
                        {(item.score * 100).toFixed(1)}
                      </span>
                    </td>
                  </tr>
                ))}
              </TitanTable>
            )}
          </div>
        </TitanPanel>
      </div>

      <TitanPanel>
        <div style={{ padding: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ margin: 0, color: 'var(--cyan)' }}>Open Alerts</h2>
            <a
              href="/alerts"
              style={{
                color: 'var(--cyan)',
                textDecoration: 'none',
                fontSize: '0.875rem',
                textShadow: 'var(--glow-cyan)'
              }}
            >
              View all →
            </a>
          </div>
          {alertsError && (
            <div style={{
              padding: '1rem',
              background: 'rgba(217, 70, 239, 0.2)',
              color: 'var(--magenta)',
              borderRadius: '6px',
              border: '1px solid var(--magenta)'
            }}>
              {alertsError}
            </div>
          )}
          {alertsLoading && !alertsError && (
            <div style={{ color: 'var(--muted)' }}>Loading alerts...</div>
          )}
          {!alertsLoading && !alertsError && openAlerts.length === 0 && (
            <div style={{
              padding: '2rem',
              textAlign: 'center',
              color: 'var(--muted)',
              fontStyle: 'italic',
              background: 'rgba(6, 182, 212, 0.05)',
              borderRadius: '6px',
              border: '1px dashed var(--panel-border)'
            }}>
              No open alerts
            </div>
          )}
          {!alertsLoading && !alertsError && openAlerts.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {openAlerts.map((alert) => (
                <div
                  key={alert.id}
                  style={{
                    padding: '0.75rem',
                    background: 'rgba(6, 182, 212, 0.1)',
                    borderLeft: `4px solid ${alert.severity === 'critical' ? 'var(--magenta)' :
                                 alert.severity === 'warning' ? 'var(--amber)' : 'var(--cyan)'}`,
                    borderRadius: '4px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    transition: 'all 0.2s'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'rgba(6, 182, 212, 0.2)'
                    e.currentTarget.style.boxShadow = 'var(--glow-cyan)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'rgba(6, 182, 212, 0.1)'
                    e.currentTarget.style.boxShadow = 'none'
                  }}
                >
                  <div>
                    <div style={{ fontWeight: '500', fontSize: '0.875rem' }}>
                      {alert.message}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '0.25rem' }}>
                      Asset ID: {alert.asset_id} • {new Date(alert.triggered_at).toLocaleString()}
                    </div>
                  </div>
                  <span style={{
                    padding: '0.25rem 0.5rem',
                    background: alert.severity === 'critical' ? 'rgba(217, 70, 239, 0.2)' :
                                alert.severity === 'warning' ? 'rgba(245, 158, 11, 0.2)' :
                                'rgba(6, 182, 212, 0.2)',
                    color: alert.severity === 'critical' ? 'var(--magenta)' :
                           alert.severity === 'warning' ? 'var(--amber)' :
                           'var(--cyan)',
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
      </TitanPanel>
    </div>
  )
}
