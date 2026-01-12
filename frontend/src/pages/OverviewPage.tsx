import { useEffect, useState } from 'react'
import { apiClient } from '../lib/api'
import type { Asset } from '../api/types'

export function OverviewPage() {
  const [stats, setStats] = useState({
    totalAssets: 0,
    totalGroups: 0,
    loading: true
  })
  
  const [recentAssets, setRecentAssets] = useState<Asset[]>([])
  
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
    </div>
  )
}
