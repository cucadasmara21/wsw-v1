import React, { useEffect, useState } from 'react'
import { fetchApiJson } from '../lib/api'
// TODO: Migrate to typed client:
// import { typedGet, type Asset } from '../api/client'
import TableList from '../components/TableList'

type Asset = { id?: number; symbol?: string; name?: string; exchange?: string; country?: string; is_active?: boolean }

export default function AssetsPage(){
  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string|null>(null)

  useEffect(()=>{ (async ()=>{
    setLoading(true)
    try{
      const data = await fetchApiJson<Asset[]>('/assets')
      setAssets(data)
    }catch(e:any){ setError(e.message) }
    setLoading(false)
  })() }, [])

  if (loading) return <div>Loading assets...</div>
  if (error) return <div className="error">Error: {error}</div>

  return (
    <div>
      <h2>Assets</h2>
      <TableList
        columns={["id","symbol","name","exchange","country","is_active"]}
        rows={assets}
        renderCell={(row, col) => {
          const v = (row as any)[col]
          if (typeof v === 'boolean') return v ? 'Yes' : 'No'
          return v ?? '-'
        }}
      />
      <button onClick={()=> window.location.reload()}>Refresh</button>
    </div>
  )
}
