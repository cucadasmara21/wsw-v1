import React, { useEffect, useState } from 'react'

type Asset = {
  id?: number
  symbol?: string
  name?: string
  sector?: string
}

export default function Assets(){
  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchAssets = async () => {
    setLoading(true)
    setError(null)
    try{
      const res = await fetch('/api/assets')
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const data = await res.json()
      setAssets(data)
    }catch(e: any){
      setError(e.message)
    }finally{
      setLoading(false)
    }
  }

  useEffect(()=>{ fetchAssets() }, [])

  if (loading) return <div>Loading assets...</div>
  if (error) return <div className="error">Error: {error}</div>

  return (
    <div>
      {assets.length === 0 ? (
        <div>No assets yet</div>
      ) : (
        <table>
          <thead>
            <tr><th>ID</th><th>Symbol</th><th>Name</th><th>Sector</th></tr>
          </thead>
          <tbody>
            {assets.map((a, idx) => (
              <tr key={a.id ?? idx}>
                <td>{a.id}</td>
                <td>{a.symbol}</td>
                <td>{a.name}</td>
                <td>{a.sector}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <button onClick={fetchAssets}>Refresh</button>
    </div>
  )
}