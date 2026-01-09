export const API_BASE = import.meta.env.VITE_API_URL ?? '/api'

/** Ensure base and path are joined with a single slash */
function joinPath(base: string, path: string) {
  if (!base.endsWith('/')) base = base + '/'
  if (path.startsWith('/')) path = path.slice(1)
  return base + path
}

/**
 * Fetch relative to API base. Pass a path starting with '/' (e.g. '/assets')
 * which will be requested as `${API_BASE}${path}`. Throws on non-ok.
 */
export async function fetchApiJson<T = any>(path: string, init?: RequestInit) {
  const url = joinPath(API_BASE, path)
  const res = await fetch(url, init)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 200)}`)
  }
  return res.json() as Promise<T>
}

/**
 * Low-level fetch returning Response for callers that need to inspect status (e.g. 404 handling)
 */
export async function fetchApiRaw(path: string, init?: RequestInit) {
  const url = joinPath(API_BASE, path)
  return fetch(url, init)
}

/**
 * Fetch from root (use for /health, /version)
 */
export async function fetchRootJson<T = any>(path: string, init?: RequestInit) {
  const res = await fetch(path, init)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 200)}`)
  }
  return res.json() as Promise<T>
}
