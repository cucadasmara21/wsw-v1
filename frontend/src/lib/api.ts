// Normalize API path: ensure it starts with /api (proxy-only routing)
function normalizeApiPath(path: string): string {
  if (path.startsWith('/api/')) return path
  if (path === '/api') return '/api'
  if (path.startsWith('/')) return `/api${path}`
  return `/api/${path}`
}

export async function fetchApiJson<T = any>(path: string, init?: RequestInit) {
  // Use relative path - Vite proxy handles routing to backend
  const finalUrl = normalizeApiPath(path)
  
  // DEV-only debug for assets fetch
  if (import.meta.env.DEV && path.includes('assets')) {
    console.debug('[fetchAssets] finalUrl=', finalUrl, 'status=...')
  }
  
  const res = await fetch(finalUrl, init)
  if (!res.ok) {
    const text = await res.text()
    let errorData
    try {
      errorData = JSON.parse(text)
    } catch {
      errorData = { message: text.slice(0, 200) }
    }
    throw errorData
  }
  
  // DEV-only: log status after fetch completes
  if (import.meta.env.DEV && path.includes('assets')) {
    console.debug('[fetchAssets] finalUrl=', finalUrl, 'status=', res.status)
  }
  
  return res.json() as Promise<T>
}

export async function fetchApiRaw(path: string, init?: RequestInit) {
  // Use relative path - Vite proxy handles routing to backend
  const finalUrl = normalizeApiPath(path)
  return fetch(finalUrl, init)
}

export async function fetchApiArrayBuffer(path: string, init?: RequestInit) {
  // Use relative path - Vite proxy handles routing to backend
  const finalUrl = normalizeApiPath(path)
  const res = await fetch(finalUrl, init)
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`)
  }
  return res.arrayBuffer()
}

export async function fetchRootJson<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`)
  return (await res.json()) as T
}

export const apiClient = {
  async get<T>(path: string): Promise<T> {
    return fetchApiJson<T>(path)
  },

  async post<T>(path: string, body: any): Promise<T> {
    return fetchApiJson<T>(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
  },

  async getHealth() {
    return fetchApiJson<{ status: string; timestamp: string; services: any }>('/health')
  },

  async getUniverseTree() {
    return fetchApiJson<any>('/universe/tree')
  },

  // Route A: legacy universe points endpoints removed. Use V8 snapshot/health only.

  async getAssetDetail(symbol: string) {
    return fetchApiJson<{
      symbol: string
      name: string
      lastPrice: number
      changePercent: number
      sparkline: number[]
    }>(`/assets/detail?symbol=${encodeURIComponent(symbol)}`)
  }
}
