import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiClient } from '../lib/api'
import { previewCategorySelection, recomputeCategorySelection } from '../api/client'
import type { UniverseTree, Asset } from '../api/types'
import type { CategorySelection, SelectionItem } from '../api/types'

export function UniversePage() {
  const navigate = useNavigate()
  const [tree, setTree] = useState<UniverseTree | null>(null)
  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedCategory, setSelectedCategory] = useState<number | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  
  // Selection state
  const [selection, setSelection] = useState<CategorySelection | null>(null)
  const [selectionLoading, setSelectionLoading] = useState(false)
  const [selectionError, setSelectionError] = useState<string | null>(null)
  const [recomputeLoading, setRecomputeLoading] = useState(false)
  
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
  
  // Load selection when category is selected
  useEffect(() => {
    async function loadSelection() {
      if (!selectedCategory) {
        setSelection(null)
        return
      }
      
      setSelectionLoading(true)
      setSelectionError(null)
      try {
        const data = await previewCategorySelection(selectedCategory, { top_n: 10, lookback_days: 90 })
        setSelection(data)
      } catch (err: any) {
        setSelectionError(err.message || 'Failed to load selection')
        setSelection(null)
      } finally {
        setSelectionLoading(false)
      }
    }
    
    loadSelection()
  }, [selectedCategory])
  
  const handleRecompute = async () => {
    if (!selectedCategory) return
    
    setRecomputeLoading(true)
    setSelectionError(null)
    try {
      const data = await recomputeCategorySelection(selectedCategory, { top_n: 10, lookback_days: 90 })
      setSelection(data)
    } catch (err: any) {
      setSelectionError(err.message || 'Failed to recompute selection')
    } finally {
      setRecomputeLoading(false)
    }
  }
  
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
      
      {/* Right panel: Assets + Selection */}
      <div style={{ flex: 1, padding: '1.5rem', overflowY: 'auto' }}>
        {/* Selection Panel (when category selected) */}
        {selectedCategory && (
          <div style={{ marginBottom: '2rem', background: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0 }}>Top 10 Selection</h3>
              <button 
                onClick={handleRecompute}
                disabled={recomputeLoading}
                style={{ 
                  padding: '0.5rem 1rem',
                  background: recomputeLoading ? '#94a3b8' : '#3b82f6',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: recomputeLoading ? 'not-allowed' : 'pointer',
                  fontWeight: '500'
                }}
              >
                {recomputeLoading ? 'Recomputing...' : 'Recompute Selection'}
              </button>
            </div>
            
            {selectionError && (
              <div style={{ padding: '0.75rem', background: '#fee2e2', border: '1px solid #fecaca', borderRadius: '6px', marginBottom: '1rem', color: '#991b1b' }}>
                {selectionError}
              </div>
            )}
            
            {selectionLoading ? (
              <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>Loading selection...</div>
            ) : selection && selection.selected.length > 0 ? (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #e2e8f0', background: '#f8fafc' }}>
                    <th style={{ textAlign: 'left', padding: '0.5rem' }}>Rank</th>
                    <th style={{ textAlign: 'left', padding: '0.5rem' }}>Symbol</th>
                    <th style={{ textAlign: 'left', padding: '0.5rem' }}>Name</th>
                    <th style={{ textAlign: 'right', padding: '0.5rem' }}>Score</th>
                    <th style={{ textAlign: 'left', padding: '0.5rem' }}>Top Drivers</th>
                    <th style={{ textAlign: 'center', padding: '0.5rem' }}>Data</th>
                  </tr>
                </thead>
                <tbody>
                  {selection.selected.map((item: SelectionItem) => {
                    const topDrivers = Object.entries(item.explain || {})
                      .filter(([key]) => key !== 'total' && key !== 'error')
                      .sort((a, b) => (b[1] as number) - (a[1] as number))
                      .slice(0, 3)
                      .map(([key]) => key)
                      .join(', ')
                    
                    return (
                      <tr key={item.asset_id} style={{ borderBottom: '1px solid #e2e8f0' }}>
                        <td style={{ padding: '0.5rem', fontWeight: '500' }}>{item.rank}</td>
                        <td style={{ padding: '0.5rem', color: '#3b82f6', fontWeight: '500' }}>{item.symbol}</td>
                        <td style={{ padding: '0.5rem' }}>{item.name}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', fontFamily: 'monospace' }}>
                          {item.score.toFixed(3)}
                        </td>
                        <td style={{ padding: '0.5rem', fontSize: '0.75rem', color: '#64748b' }}>
                          {topDrivers || 'N/A'}
                        </td>
                        <td style={{ padding: '0.5rem', textAlign: 'center', fontSize: '0.75rem' }}>
                          {item.data_meta?.stale && (
                            <span style={{ background: '#fef3c7', padding: '0.125rem 0.375rem', borderRadius: '4px', marginRight: '0.25rem' }}>
                              📦 stale
                            </span>
                          )}
                          {item.data_meta?.cached && !item.data_meta?.stale && (
                            <span style={{ background: '#dbeafe', padding: '0.125rem 0.375rem', borderRadius: '4px' }}>
                              ⚡ cached
                            </span>
                          )}
                          {item.data_meta?.confidence !== undefined && item.data_meta.confidence < 0.5 && (
                            <span style={{ background: '#fee2e2', padding: '0.125rem 0.375rem', borderRadius: '4px' }}>
                              ⚠️ low conf
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            ) : (
              <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>
                No selection data available for this category
              </div>
            )}
          </div>
        )}
        
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
