import React, { useEffect, useState } from 'react'
import { fetchJson } from '../lib/api'
import TableList from '../components/TableList'

type Asset = { id?: number; symbol?: string; name?: string; sector?: string }

export default function AssetsPage(){
  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string|null>(null)

  useEffect(()=>{ (async ()=>{
    setLoading(true)
    try{
      const data = await fetchJson<Asset[]>('/assets')
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
        columns={["id","symbol","name","sector"]}
        rows={assets}
        renderCell={(row, col) => (row as any)[col] ?? '-'}
      />
      <button onClick={()=> window.location.reload()}>Refresh</button>
    </div>
  )
}
