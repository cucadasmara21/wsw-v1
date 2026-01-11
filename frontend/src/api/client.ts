/**
 * Typed API client using OpenAPI-generated types
 * 
 * This provides a minimal typed wrapper around the API.
 * For full type safety, import `paths` from './generated' and use with a fetch wrapper.
 */
import type { paths, components } from './generated'

export const API_BASE = import.meta.env.VITE_API_URL ?? '/api'

/** Ensure base and path are joined with a single slash */
function joinPath(base: string, path: string) {
  if (!base.endsWith('/')) base = base + '/'
  if (path.startsWith('/')) path = path.slice(1)
  return base + path
}

/**
 * Generic typed fetch for GET endpoints
 * 
 * @example
 * const assets = await typedGet<Asset[]>('/assets')
 */
export async function typedGet<T>(path: string, init?: RequestInit): Promise<T> {
  const url = joinPath(API_BASE, path)
  const res = await fetch(url, { ...init, method: 'GET' })
  
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 200)}`)
  }
  
  return res.json() as Promise<T>
}

/**
 * Generic typed fetch for POST endpoints
 */
export async function typedPost<TBody, TResponse>(
  path: string,
  body: TBody,
  init?: RequestInit
): Promise<TResponse> {
  const url = joinPath(API_BASE, path)
  const res = await fetch(url, {
    ...init,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
    body: JSON.stringify(body),
  })
  
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 200)}`)
  }
  
  return res.json() as Promise<TResponse>
}

/**
 * Low-level fetch returning Response for callers that need to inspect status (e.g. 404 handling)
 */
export async function fetchRaw(path: string, init?: RequestInit) {
  const url = joinPath(API_BASE, path)
  return fetch(url, init)
}

// Re-export types for convenience
export type { paths, components }

// Example: Extract specific schema types
export type Asset = components['schemas']['AssetSchema']
export type HealthResponse = components['schemas']['HealthResponse']
export type VersionResponse = components['schemas']['VersionResponse']
