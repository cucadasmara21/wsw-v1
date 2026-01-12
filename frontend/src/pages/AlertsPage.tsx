import { useState, useEffect } from 'react'
import { typedGet, typedPost } from '../api/client'
import type { AlertOut, Asset } from '../api/types'
import '../components/Layout.css'

export function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertOut[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [filters, setFilters] = useState({
    severity: '',
    status: 'active', // 'active' | 'resolved' | 'all'
    assetId: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [confirmRecompute, setConfirmRecompute] = useState(false)

  // Load assets
  useEffect(() => {
    const loadAssets = async () => {
      try {
        const data = await typedGet<Asset[]>('/assets')
        setAssets(data || [])
      } catch (err) {
        console.error('Failed to load assets:', err)
      }
    }
    loadAssets()
  }, [])

  // Load alerts
  const loadAlerts = async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (filters.severity) params.append('severity', filters.severity)
      if (filters.status === 'active') params.append('active', 'true')
      if (filters.status === 'resolved') params.append('active', 'false')
      if (filters.assetId) params.append('asset_id', filters.assetId)

      const query = params.toString() ? `?${params.toString()}` : ''
      const data = await typedGet<AlertOut[]>(`/alerts${query}`)
      setAlerts(data || [])
    } catch (err: any) {
      if (err.message.includes('401')) {
        setError('Unauthorized: Please log in')
      } else if (err.message.includes('403')) {
        setError('Access denied')
      } else if (err.message.includes('429')) {
        setError('Rate limit exceeded. Please wait before refreshing.')
      } else if (err.message.includes('503')) {
        setError('Service temporarily unavailable')
      } else {
        setError(`Failed to load alerts: ${err.message}`)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAlerts()
  }, [filters])

  const handleResolveAlert = async (alertId: number) => {
    setError(null)
    try {
      await typedPost<void, AlertOut>(`/alerts/${alertId}/resolve`, {})
      setMessage('Alert resolved successfully')
      setTimeout(() => setMessage(null), 2000)
      await loadAlerts()
    } catch (err: any) {
      if (err.message.includes('403')) {
        setError('You do not have permission to resolve alerts')
      } else if (err.message.includes('429')) {
        setError('Too many requests. Please wait.')
      } else {
        setError(`Failed to resolve alert: ${err.message}`)
      }
    }
  }

  const handleRecomputeAlerts = async () => {
    setLoading(true)
    setError(null)
    try {
      await typedPost<void, { status: string }>('/alerts/recompute', {})
      setMessage('Alert recomputation queued successfully')
      setConfirmRecompute(false)
      setTimeout(() => {
        setMessage(null)
        loadAlerts()
      }, 2000)
    } catch (err: any) {
      if (err.message.includes('403')) {
        setError('You do not have permission to recompute alerts')
      } else if (err.message.includes('429')) {
        setError('Too many requests. Please wait.')
      } else if (err.message.includes('503')) {
        setError('Service temporarily unavailable')
      } else {
        setError(`Failed to recompute alerts: ${err.message}`)
      }
    } finally {
      setLoading(false)
    }
  }

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical':
        return '#dc3545'
      case 'warning':
        return '#ffc107'
      case 'info':
        return '#17a2b8'
      default:
        return '#6c757d'
    }
  }

  const getAssetName = (assetId: number) => {
    const asset = assets.find((a) => a.id === assetId)
    return asset ? `${asset.symbol}` : `Asset ${assetId}`
  }

  return (
    <div className="container">
      <h1>Alerts</h1>

      {/* Messages */}
      {error && (
        <div
          style={{
            padding: '12px',
            marginBottom: '20px',
            backgroundColor: '#fee',
            border: '1px solid #f88',
            borderRadius: '4px',
            color: '#c33',
          }}
        >
          {error}
        </div>
      )}
      {message && (
        <div
          style={{
            padding: '12px',
            marginBottom: '20px',
            backgroundColor: '#efe',
            border: '1px solid #8f8',
            borderRadius: '4px',
            color: '#3c3',
          }}
        >
          {message}
        </div>
      )}

      {/* Filters */}
      <div className="card" style={{ marginBottom: '20px' }}>
        <h3>Filters</h3>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
            gap: '10px',
          }}
        >
          <div>
            <label>Status</label>
            <select
              value={filters.status}
              onChange={(e) => setFilters({ ...filters, status: e.target.value })}
              style={{
                width: '100%',
                padding: '8px',
                borderRadius: '4px',
                border: '1px solid #ddd',
                boxSizing: 'border-box',
              }}
            >
              <option value="active">Active</option>
              <option value="resolved">Resolved</option>
              <option value="all">All</option>
            </select>
          </div>

          <div>
            <label>Severity</label>
            <select
              value={filters.severity}
              onChange={(e) => setFilters({ ...filters, severity: e.target.value })}
              style={{
                width: '100%',
                padding: '8px',
                borderRadius: '4px',
                border: '1px solid #ddd',
                boxSizing: 'border-box',
              }}
            >
              <option value="">All</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="critical">Critical</option>
            </select>
          </div>

          <div>
            <label>Asset</label>
            <select
              value={filters.assetId}
              onChange={(e) => setFilters({ ...filters, assetId: e.target.value })}
              style={{
                width: '100%',
                padding: '8px',
                borderRadius: '4px',
                border: '1px solid #ddd',
                boxSizing: 'border-box',
              }}
            >
              <option value="">All Assets</option>
              {assets.map((asset) => (
                <option key={asset.id} value={asset.id}>
                  {asset.symbol}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Recompute Button */}
      <div style={{ marginBottom: '20px' }}>
        <button
          onClick={() => setConfirmRecompute(true)}
          disabled={loading || confirmRecompute}
          style={{
            padding: '10px 20px',
            backgroundColor: '#28a745',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: loading || confirmRecompute ? 'not-allowed' : 'pointer',
            opacity: loading || confirmRecompute ? 0.6 : 1,
          }}
        >
          Recompute All Alerts
        </button>

        {confirmRecompute && (
          <div style={{ marginTop: '10px', padding: '10px', backgroundColor: '#fff3cd', borderRadius: '4px' }}>
            <p>Are you sure you want to recompute all alerts?</p>
            <button
              onClick={handleRecomputeAlerts}
              disabled={loading}
              style={{
                padding: '8px 16px',
                marginRight: '10px',
                backgroundColor: '#28a745',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: loading ? 'not-allowed' : 'pointer',
              }}
            >
              {loading ? 'Processing...' : 'Confirm'}
            </button>
            <button
              onClick={() => setConfirmRecompute(false)}
              disabled={loading}
              style={{
                padding: '8px 16px',
                backgroundColor: '#6c757d',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      {/* Alerts Table */}
      {loading ? (
        <p>Loading alerts...</p>
      ) : alerts.length === 0 ? (
        <div className="card">
          <p style={{ color: '#666' }}>No alerts found matching your filters.</p>
        </div>
      ) : (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
            }}
          >
            <thead>
              <tr style={{ borderBottom: '2px solid #ddd' }}>
                <th style={{ textAlign: 'left', padding: '10px' }}>Triggered</th>
                <th style={{ textAlign: 'left', padding: '10px' }}>Asset</th>
                <th style={{ textAlign: 'left', padding: '10px' }}>Type</th>
                <th style={{ textAlign: 'left', padding: '10px' }}>Severity</th>
                <th style={{ textAlign: 'left', padding: '10px' }}>Message</th>
                <th style={{ textAlign: 'left', padding: '10px' }}>Status</th>
                <th style={{ textAlign: 'left', padding: '10px' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert) => (
                <tr key={alert.id} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: '10px', fontSize: '0.9em' }}>
                    {new Date(alert.triggered_at).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px' }}>{getAssetName(alert.asset_id)}</td>
                  <td style={{ padding: '10px' }}>{alert.key}</td>
                  <td style={{ padding: '10px' }}>
                    <span
                      style={{
                        padding: '4px 8px',
                        borderRadius: '4px',
                        color: 'white',
                        backgroundColor: getSeverityColor(alert.severity),
                        fontSize: '0.85em',
                      }}
                    >
                      {alert.severity}
                    </span>
                  </td>
                  <td style={{ padding: '10px' }}>{alert.message}</td>
                  <td style={{ padding: '10px' }}>
                    {alert.resolved_at ? (
                      <span style={{ color: '#28a745' }}>✓ Resolved</span>
                    ) : (
                      <span style={{ color: '#dc3545' }}>Open</span>
                    )}
                  </td>
                  <td style={{ padding: '10px' }}>
                    {!alert.resolved_at && (
                      <button
                        onClick={() => handleResolveAlert(alert.id)}
                        disabled={loading}
                        style={{
                          padding: '6px 12px',
                          backgroundColor: '#28a745',
                          color: 'white',
                          border: 'none',
                          borderRadius: '4px',
                          cursor: loading ? 'not-allowed' : 'pointer',
                          fontSize: '0.9em',
                        }}
                      >
                        Resolve
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
