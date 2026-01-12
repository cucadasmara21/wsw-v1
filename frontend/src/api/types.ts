/**
 * Stable type aliases from OpenAPI-generated types
 * Re-export key schemas for use in the app
 */
import type { components } from './generated'

// Asset schemas
export type Asset = components['schemas']['Asset']
export type AssetDetail = components['schemas']['AssetDetail']
export type AssetCreate = components['schemas']['AssetCreate']

// Ontology schemas  
export type GroupNode = components['schemas']['GroupNode']
export type SubgroupNode = components['schemas']['SubgroupNode']
export type CategoryNode = components['schemas']['CategoryNode']
export type UniverseTree = components['schemas']['UniverseTreeResponse']

// Auth schemas
export type User = components['schemas']['User']
export type Token = components['schemas']['Token']

// Market schemas
export type MarketBar = components['schemas']['MarketBar']
export type MarketBars = components['schemas']['MarketBarsResponse']
export type MarketIndicators = components['schemas']['MarketIndicators']
export type MarketRisk = components['schemas']['MarketRisk']
export type MarketRiskComponents = components['schemas']['MarketRiskComponents']
export type MarketSnapshot = components['schemas']['MarketSnapshotResponse']

// Metrics schemas
export type MetricSnapshotOut = {
  id: number
  asset_id: number
  as_of: string
  metrics: Record<string, number>
  score: number
  explain: {
    items?: Array<{
      metric_id: string
      raw_value: number
      normalized_score: number
      weight: number
      contribution: number
    }>
  }
  created_at: string
}

export type LeaderboardItem = {
  asset_id: number
  symbol: string
  name: string | null
  score: number
}

// Alert schemas
export type AlertOut = {
  id: number
  asset_id: number
  key: string
  severity: string
  message: string
  triggered_at: string
  resolved_at: string | null
  payload: Record<string, any>
}

// Validation schemas
export type ValidationError = components['schemas']['ValidationError']
export type HTTPValidationError = components['schemas']['HTTPValidationError']
