import { useEffect, useState } from 'react'

interface HUDStats {
  sync: 'LIVE' | 'OFFLINE'
  ws: 'CONNECTED' | 'DOWN'
  stride: string
  points: number
  lat: number | null
  fps: number | null
  lastFetchMs: number | null
}

export function SovereignHUD() {
  const [stats, setStats] = useState<HUDStats>({
    sync: 'OFFLINE',
    ws: 'DOWN',
    stride: '12B',
    points: 0,
    lat: null,
    fps: null,
    lastFetchMs: null
  })

  useEffect(() => {
    let frameCount = 0
    let lastTime = performance.now()
    let fpsValue: number | null = null

    const updateFPS = () => {
      frameCount++
      const now = performance.now()
      if (now - lastTime >= 1000) {
        fpsValue = Math.round((frameCount * 1000) / (now - lastTime))
        frameCount = 0
        lastTime = now
        setStats(prev => ({ ...prev, fps: fpsValue }))
      }
      requestAnimationFrame(updateFPS)
    }
    updateFPS()

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/v1/telemetry`
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      setStats(prev => ({ ...prev, ws: 'CONNECTED', sync: 'LIVE' }))
    }

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'heartbeat') {
          setStats(prev => ({
            ...prev,
            points: msg.points_count || prev.points,
            sync: 'LIVE'
          }))
        }
      } catch (err) {
        console.error('Failed to parse telemetry:', err)
      }
    }

    ws.onerror = () => {
      setStats(prev => ({ ...prev, ws: 'DOWN', sync: 'OFFLINE' }))
    }

    ws.onclose = () => {
      setStats(prev => ({ ...prev, ws: 'DOWN', sync: 'OFFLINE' }))
    }

    const healthCheck = async () => {
      try {
        const start = performance.now()
        const res = await fetch('/api/health')
        const lat = Math.round(performance.now() - start)
        if (res.ok) {
          setStats(prev => ({ ...prev, lat, sync: 'LIVE' }))
        } else {
          setStats(prev => ({ ...prev, sync: 'OFFLINE' }))
        }
      } catch {
        setStats(prev => ({ ...prev, sync: 'OFFLINE' }))
      }
    }

    const healthInterval = setInterval(healthCheck, 5000)
    healthCheck()

    return () => {
      clearInterval(healthInterval)
      ws.close()
    }
  }, [])

  return (
    <div className="sovereign-hud">
      <div className="sovereign-hud-item">
        <span className="sovereign-hud-label">SYNC</span>
        <span className={`sovereign-hud-value ${stats.sync === 'LIVE' ? 'live' : 'offline'}`}>
          {stats.sync}
        </span>
      </div>
      <div className="sovereign-hud-item">
        <span className="sovereign-hud-label">WS</span>
        <span className={`sovereign-hud-value ${stats.ws === 'CONNECTED' ? 'live' : 'offline'}`}>
          {stats.ws}
        </span>
      </div>
      <div className="sovereign-hud-item">
        <span className="sovereign-hud-label">STRIDE</span>
        <span className="sovereign-hud-value">{stats.stride}</span>
      </div>
      <div className="sovereign-hud-item">
        <span className="sovereign-hud-label">POINTS</span>
        <span className="sovereign-hud-value">{stats.points.toLocaleString()}</span>
      </div>
      {stats.lat !== null && (
        <div className="sovereign-hud-item">
          <span className="sovereign-hud-label">LAT</span>
          <span className="sovereign-hud-value">{stats.lat}ms</span>
        </div>
      )}
      {stats.fps !== null && (
        <div className="sovereign-hud-item">
          <span className="sovereign-hud-label">FPS</span>
          <span className="sovereign-hud-value">{stats.fps}</span>
        </div>
      )}
    </div>
  )
}
