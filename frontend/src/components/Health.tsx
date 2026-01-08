import React, { useEffect, useState } from 'react'

type Health = {
  status: string
  timestamp: string
  services: Record<string, string>
}

export default function Health() {
  const [health, setHealth] = useState<Health | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchHealth = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/health')
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const data = await res.json()
      setHealth(data)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchHealth()
  }, [])

  if (loading) return <div>Loading...</div>
  if (error) return (
    <div>
      <div className="error">Error: {error}</div>
      <button onClick={fetchHealth}>Retry</button>
    </div>
  )

  if (!health) return null

  return (
    <div>
      <div>Status: <strong>{health.status}</strong></div>
      <div>Timestamp: {health.timestamp}</div>
      <div>Services:</div>
      <ul>
        {Object.entries(health.services).map(([k, v]) => (
          <li key={k}>{k}: {v}</li>
        ))}
      </ul>
      <button onClick={fetchHealth}>Refresh</button>
    </div>
  )
}
