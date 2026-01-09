import React, { useEffect, useState } from 'react'
import { fetchJson } from '../lib/api'

type Asset = { id?: number; symbol?: string; name?: string }

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
  if (error) return <div>Error: {error}</div>

  return (
    <div>
      <h2>Assets</h2>
      {assets.length === 0 ? <div>No assets yet</div> : (
        <ul>{assets.map(a=> <li key={a.id}>{a.symbol} — {a.name}</li>)}</ul>
      )}
      <button onClick={()=> window.location.reload()}>Refresh</button>
    </div>
  )
}
