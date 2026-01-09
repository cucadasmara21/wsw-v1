export const API_BASE = import.meta.env.VITE_API_URL ?? '/api'

/**
 * Fetch relative to API base. Pass a path starting with '/' (e.g. '/assets')
 * which will be requested as `${API_BASE}${path}`.
 */
export async function fetchJson<T = any>(path: string) {
  const url = `${API_BASE}${path}`
  const res = await fetch(url)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 200)}`)
  }
  return res.json() as Promise<T>
}

/**
 * Fetch from root (use for /health, /version)
 */
export async function fetchRootJson<T = any>(path: string) {
  const res = await fetch(path)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 200)}`)
  }
  return res.json() as Promise<T>
}
