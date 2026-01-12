import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiClient } from '../lib/api'
import type { UniverseTree, Asset } from '../api/types'

export function UniversePage() {
  const navigate = useNavigate()
  const [tree, setTree] = useState<UniverseTree | null>(null)
  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedCategory, setSelectedCategory] = useState<number | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  
  useEffect(() => {
    async function loadTree() {
      try {
        const data = await apiClient.get<UniverseTree>('/api/universe/tree')
        setTree(data)
      } catch (err) {
        console.error('Failed to load universe tree:', err)
      } finally {
        setLoading(false)
      }
    }
    
    loadTree()
  }, [])
  
  useEffect(() => {
    async function loadAssets() {
      try {
        let url = '/api/assets/?limit=50'
        if (selectedCategory) {
          url += `&category_id=${selectedCategory}`
        }
        if (searchQuery) {
          url += `&q=${encodeURIComponent(searchQuery)}`
        }
        
        const data = await apiClient.get<Asset[]>(url)
        setAssets(data)
      } catch (err) {
        console.error('Failed to load assets:', err)
      }
    }
    
    loadAssets()
  }, [selectedCategory, searchQuery])
  
  if (loading) {
    return <div style={{ padding: '2rem' }}>Loading universe...</div>
  }
  
  return (
    <div style={{ display: 'flex', height: '100%' }}>
      {/* Left panel: Tree */}
      <div style={{ width: '300px', background: 'white', borderRight: '1px solid #e2e8f0', overflowY: 'auto', padding: '1rem' }}>
        <h3 style={{ marginTop: 0 }}>Universe Tree</h3>
        
        {tree?.groups.map(group => (
          <details key={group.id} open style={{ marginBottom: '1rem' }}>
            <summary style={{ fontWeight: 'bold', cursor: 'pointer', padding: '0.5rem', background: '#f1f5f9', borderRadius: '4px' }}>
              {group.name}
            </summary>
            <div style={{ paddingLeft: '1rem', marginTop: '0.5rem' }}>
              {group.subgroups.map(subgroup => (
                <details key={subgroup.id} style={{ marginBottom: '0.5rem' }}>
                  <summary style={{ cursor: 'pointer', padding: '0.25rem' }}>
                    {subgroup.name}
                  </summary>
                  <div style={{ paddingLeft: '1rem', marginTop: '0.25rem' }}>
                    {subgroup.categories.map(category => (
                      <div 
                        key={category.id}
                        onClick={() => setSelectedCategory(category.id)}
                        style={{ 
                          padding: '0.25rem 0.5rem',
                          cursor: 'pointer',
                          background: selectedCategory === category.id ? '#dbeafe' : 'transparent',
                          borderRadius: '4px',
                          fontSize: '0.875rem'
                        }}
                      >
                        {category.name}
                      </div>
                    ))}
                  </div>
                </details>
              ))}
            </div>
          </details>
        ))}
      </div>
      
      {/* Right panel: Assets */}
      <div style={{ flex: 1, padding: '1.5rem', overflowY: 'auto' }}>
        <div style={{ marginBottom: '1rem', display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <input 
            type="search"
            placeholder="Search assets..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ 
              flex: 1,
              padding: '0.5rem 1rem',
              border: '1px solid #cbd5e1',
              borderRadius: '6px',
              fontSize: '1rem'
            }}
          />
          {selectedCategory && (
            <button 
              onClick={() => setSelectedCategory(null)}
              style={{ 
                padding: '0.5rem 1rem',
                background: '#64748b',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer'
              }}
            >
              Clear Filter
            </button>
          )}
        </div>
        
        <div style={{ background: 'white', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
                <th style={{ textAlign: 'left', padding: '0.75rem' }}>Symbol</th>
                <th style={{ textAlign: 'left', padding: '0.75rem' }}>Name</th>
                <th style={{ textAlign: 'left', padding: '0.75rem' }}>Sector</th>
                <th style={{ textAlign: 'left', padding: '0.75rem' }}>Exchange</th>
              </tr>
            </thead>
            <tbody>
              {assets.map(asset => (
                <tr 
                  key={asset.id} 
                  onClick={() => navigate(`/assets/${asset.id}`)}
                  style={{ 
                    borderBottom: '1px solid #e2e8f0',
                    cursor: 'pointer',
                    transition: 'background 0.2s'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = '#f8fafc'}
                  onMouseLeave={(e) => e.currentTarget.style.background = 'white'}
                >
                  <td style={{ padding: '0.75rem', fontWeight: '500', color: '#3b82f6' }}>{asset.symbol}</td>
                  <td style={{ padding: '0.75rem' }}>{asset.name}</td>
                  <td style={{ padding: '0.75rem' }}>{asset.sector}</td>
                  <td style={{ padding: '0.75rem' }}>{asset.exchange}</td>
                </tr>
              ))}
            </tbody>
          </table>
          
          {assets.length === 0 && (
            <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>
              No assets found
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
