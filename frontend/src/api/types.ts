/**
 * Stable type aliases from OpenAPI-generated types
 * Re-export key schemas for use in the app
 */
import type { components } from './generated'

// Stable aliases for commonly used schemas
export type Asset = components['schemas']['AssetOut']
export type AssetDetail = components['schemas']['AssetDetailOut']
export type PagedAssets = components['schemas']['PagedAssetsOut']

export type User = components['schemas']['User']
export type Token = components['schemas']['Token']

export type RiskSnapshot = components['schemas']['RiskSnapshotOut']
export type RiskVector = components['schemas']['RiskVector']
export type RiskOverview = components['schemas']['RiskOverviewResponse']
export type RiskSummary = components['schemas']['RiskSummaryResponse']

export type MarketBar = components['schemas']['MarketBar']
export type MarketBars = components['schemas']['MarketBarsResponse']
export type MarketIndicators = components['schemas']['MarketIndicators']
export type MarketRisk = components['schemas']['MarketRisk']
export type MarketRiskComponents = components['schemas']['MarketRiskComponents']
export type MarketSnapshot = components['schemas']['MarketSnapshotResponse']

export type ValidationError = components['schemas']['ValidationError']
export type HTTPValidationError = components['schemas']['HTTPValidationError']
