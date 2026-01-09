import React, { useEffect, useState } from 'react'
import type { Health as HealthT, Version as VersionT } from '../api/generated'

export default function Health() {
  const [health, setHealth] = useState<HealthT | null>(null)
  const [version, setVersion] = useState<VersionT | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchHealth = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/health')
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const data = await res.json() as HealthT
      setHealth(data)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const fetchVersion = async () => {
    try {
      const res = await fetch('/version')
      if (!res.ok) return
      const data = await res.json() as VersionT
      setVersion(data)
    } catch (_) { }
  }

  useEffect(() => {
    fetchHealth()
    fetchVersion()
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
      {version && (
        <div>Version: <strong>{version.git_sha}</strong> (built {new Date(version.build_time).toLocaleString()})</div>
      )}
      <div>API Base: <code>{import.meta.env.VITE_API_URL ?? '/api'}</code></div>
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
