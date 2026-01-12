/**
 * Typed API client using OpenAPI-generated types
 * 
 * This provides a minimal typed wrapper around the API.
 * For full type safety, import types from './types' and paths from './generated'.
 */
import type { paths } from './generated'
import type {
  Asset,
  MarketBars,
  MarketSnapshot,
  RiskOverview,
  RiskSummary,
  User,
  Token,
  MetricSnapshotOut,
  LeaderboardItem,
  AlertOut,
} from './types'

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
export type { paths }
export type {
  Asset,
  MarketBars,
  MarketSnapshot,
  RiskOverview,
  RiskSummary,
  User,
  Token,
  MetricSnapshotOut,
  LeaderboardItem,
  AlertOut,
}

/**
 * Get latest metric snapshot for an asset
 */
export async function getLatestMetrics(assetId: number): Promise<MetricSnapshotOut> {
  return typedGet<MetricSnapshotOut>(`/metrics/${assetId}/latest`)
}

/**
 * Recompute metrics for an asset
 */
export async function recomputeMetrics(assetId: number): Promise<MetricSnapshotOut> {
  return typedPost<{}, MetricSnapshotOut>(`/metrics/${assetId}/recompute`, {})
}

/**
 * Get leaderboard of top risk assets
 */
export async function getLeaderboard(categoryId?: number, limit: number = 10): Promise<LeaderboardItem[]> {
  const params = new URLSearchParams()
  if (categoryId !== undefined) params.set('category_id', categoryId.toString())
  params.set('limit', limit.toString())
  const query = params.toString() ? `?${params.toString()}` : ''
  return typedGet<LeaderboardItem[]>(`/metrics/leaderboard${query}`)
}

/**
 * List alerts with optional filters
 */
export async function listAlerts(filters?: {
  severity?: string
  active?: boolean
  asset_id?: number
}): Promise<any[]> {
  const params = new URLSearchParams()
  if (filters?.severity) params.set('severity', filters.severity)
  if (filters?.active !== undefined) params.set('active', filters.active.toString())
  if (filters?.asset_id) params.set('asset_id', filters.asset_id.toString())
  const query = params.toString() ? `?${params.toString()}` : ''
  return typedGet<any[]>(`/alerts${query}`)
}

/**
 * Resolve a single alert
 */
export async function resolveAlert(alertId: number): Promise<any> {
  return typedPost<{}, any>(`/alerts/${alertId}/resolve`, {})
}

/**
 * Recompute all alerts
 */
export async function recomputeAlerts(): Promise<{ status: string }> {
  return typedPost<{}, { status: string }>(`/alerts/recompute`, {})
}
