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

// Validation schemas
export type ValidationError = components['schemas']['ValidationError']
export type HTTPValidationError = components['schemas']['HTTPValidationError']
