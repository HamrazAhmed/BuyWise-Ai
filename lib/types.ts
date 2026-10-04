/**
 * lib/types.ts
 * Canonical TypeScript types matching the PRD §18 API contracts.
 * These types are shared between the frontend and the mock data.
 * The backend uses equivalent Pydantic schemas in backend/models/.
 */

// ─── Evidence ────────────────────────────────────────────────────────────────

/** Four-level evidence status used throughout the system. */
export type EvidenceStatus = 'verified' | 'supported' | 'conflicting' | 'insufficient'

/**
 * A piece of evidence backing a claim.
 * Maps to the Evidence entity in the data model.
 */
export interface Evidence {
  id: string
  productId?: string
  chunkId?: string
  sourceId?: string
  origin?: 'web' | 'curated' | 'fixture' | 'search'
  kind?: string
  claims?: Array<{ key: string; value: string }>
  /** Human-readable title of the source document. */
  title: string
  /** URL of the original source. */
  sourceUrl: string
  /** Primary = manufacturer / official; Secondary = retailer / review. */
  sourceType: 'primary' | 'secondary'
  /** Short text excerpt supporting the claim. */
  snippet: string
  /** ISO date string when this source was fetched. */
  fetchedAt: string
}

// ─── Requirements ────────────────────────────────────────────────────────────

/**
 * Priority levels used internally by the backend.
 * Maps to the API JSON values ('must', 'high', etc.).
 */
export type ApiPriority = 'must' | 'high' | 'preferred' | 'optional'

/**
 * Priority labels displayed in the frontend UI.
 * The frontend uses these for display; the API uses ApiPriority.
 */
export type UIPriority = 'Must Have' | 'High Priority' | 'Preferred' | 'Optional'

/** Map from API priority values to UI display labels. */
export const PRIORITY_LABELS: Record<ApiPriority, UIPriority> = {
  must: 'Must Have',
  high: 'High Priority',
  preferred: 'Preferred',
  optional: 'Optional',
}

/** Map from UI labels back to API values. */
export const PRIORITY_API: Record<UIPriority, ApiPriority> = {
  'Must Have': 'must',
  'High Priority': 'high',
  'Preferred': 'preferred',
  'Optional': 'optional',
}

/**
 * A structured requirement extracted from the user's natural-language request.
 * Maps to the Requirement entity in the data model.
 */
export interface Requirement {
  id?: string
  /** Canonical key (e.g. 'budget', 'ram', 'os_compatibility'). */
  key: string
  /** Comparison operator (e.g. '<=', '>=', '=', 'supports'). */
  operator: string
  /** Value string (e.g. '1000 USD', '32 GB', 'Linux'). */
  value: string
  /** Importance level. */
  priority: ApiPriority
  /** 'user' = explicitly stated; 'inferred' = suggested by the system. */
  source: 'user' | 'inferred'
  /** Whether the user has confirmed this requirement. */
  confirmed?: boolean
}

// ─── Products ─────────────────────────────────────────────────────────────────

/**
 * A specification claim for a product.
 * Maps to ProductSpecification in the data model.
 */
export interface Spec {
  /** Spec name (e.g. 'CPU', 'RAM', 'Battery'). */
  key: string
  /** Spec value string (e.g. 'Ryzen 7 7840U', '32GB DDR5'). */
  value: string
  /** Evidence quality for this specific claim. */
  status: EvidenceStatus
  /** IDs of Evidence records backing this claim. */
  evidenceIds: string[]
  /** If conflicting, both values and their source URLs. */
  conflictingValues?: Array<{ value: string; sourceUrl: string; sourceType: 'primary' | 'secondary' }>
}

/**
 * A product candidate with its verified specs.
 * Maps to the Product entity in the data model.
 */
export interface Product {
  id: string
  name: string
  brand?: string
  category?: string
  modelNumber?: string
  /** Price in USD. null if unknown or stale (>24h). */
  price: number | null
  /** ISO timestamp of the price fetch. null if unknown. */
  priceFetchedAt?: string | null
  /** Seller name. null if not available. */
  priceSeller?: string | null
  /** Human-readable summary of requirement satisfaction. */
  score: string
  /** Short display image/initials for the product card. */
  image: string
  /** Advantages relevant to the user's requirements. */
  pros: string[]
  /** Limitations relative to the user's requirements. */
  limitations: string[]
  /** Verified specifications with evidence. */
  specs: Spec[]
  evidence?: Evidence[]
  /** Canonical product page URL. */
  canonicalUrl?: string
  priceInfo?: PriceInfo | null
  reviewThemes?: ReviewTheme[]
  warranty?: Warranty | null
  returnPolicy?: ReturnPolicy | null
  mustHaveStatus?: 'met' | 'not_met' | 'uncertain'
  weightedMatchScore?: number
}

// ─── Review / Warranty / Price ────────────────────────────────────────────────

export interface PriceInfo {
  amount: number | null
  currency: string
  seller: string | null
  fetchedAt: string | null
  isStale: boolean
  sourceId?: string
}

export interface ReviewTheme {
  theme: string
  sentiment: 'positive' | 'negative' | 'mixed' | 'neutral'
  /** Labeled as opinion — never presented as fact. */
  summary: string
  sourceId?: string
}

export interface Warranty {
  durationMonths: number | null
  coverage: string | null
  conditions: string | null
  sourceId?: string
  /** If incomplete data, mark as "seller-dependent / verify". */
  completeness: 'complete' | 'partial' | 'unknown'
}

export interface ReturnPolicy {
  windowDays: number | null
  conditions: string | null
  sellerDependent: boolean
  sourceId?: string
}

// ─── Comparison ───────────────────────────────────────────────────────────────

/**
 * How a product matches a single requirement.
 * '✓' = met, '✕' = not met, '?' = uncertain/partial.
 */
export type RequirementMatch = '✓' | '✕' | '?'

/**
 * The full comparison result produced by Agent 8.
 * Stored in the comparison table and returned by GET /api/comparison/{id}.
 */
export interface Comparison {
  id: string
  requestId: string
  createdAt: string
  products: Product[]
  /** Requirement match matrix: product id → array of match symbols per requirement. */
  requirementMatches: Record<string, RequirementMatch[]>
  /** Key trade-off narrative sentences. */
  tradeoffs: string[]
  /** Per-requirement analysis across all products. */
  requirementAnalysis?: RequirementAnalysis[]
  requirements?: Requirement[]
  dataMode?: 'live' | 'demo' | 'fixture'
  notices?: string[]
  searchReport?: { status: string; summary: string; sources: Array<{url: string; title: string}>; suggestions_html: string }
}

export interface RequirementAnalysis {
  requirement: Requirement
  /** How each product performs on this requirement. */
  productAssessments: Array<{
    productId: string
    match: RequirementMatch
    explanation: string
    evidenceIds: string[]
  }>
}

// ─── API Request / Response shapes ──────────────────────────────────────────

/** POST /api/analyze-requirements — request */
export interface AnalyzeRequirementsRequest {
  text: string
}

/** POST /api/analyze-requirements — response */
export interface AnalyzeRequirementsResponse {
  requestId: string
  category: string
  requirements: Requirement[]
  /** Clarifying questions to ask the user (0–3). */
  missingInfo: string[]
  dataMode?: 'live' | 'demo' | 'fixture'
  notices?: string[]
}

/** POST /api/research-products — request */
export interface ResearchProductsRequest {
  requestId: string
  rawText?: string
  requirements: Requirement[]
}

/** POST /api/research-products — response (SSE starts immediately) */
export interface ResearchProductsResponse {
  comparisonId: string
  status: 'processing'
  streamUrl: string
}

/** SSE event types from /api/stream/{comparison_id} */
export type SSEEventType = 'status' | 'partial_result' | 'done' | 'error'
export interface SSEEvent {
  type: SSEEventType
  /** Human-readable status message (no chain-of-thought). */
  message?: string
  data?: unknown
}

/** POST /api/compare-products — request */
export interface CompareProductsRequest {
  requestId: string
  productIds: string[]
  comparisonId?: string
}

/** POST /api/follow-up — request */
export interface FollowUpRequest {
  comparisonId: string
  /** Max 500 chars. */
  question: string
}

/** POST /api/follow-up — response */
export interface FollowUpResponse {
  answer: string
  evidenceIds: string[]
  /** Whether this question requires a new research run to answer fully. */
  requiresRerun: boolean
  /** Suggested requirement patches if the user wants to regenerate. */
  suggestedRequirementsPatch?: Array<Partial<Requirement>>
}

// ─── Error shape (all API errors) ────────────────────────────────────────────

export type ApiErrorCode =
  | 'INVALID_INPUT'
  | 'NOT_FOUND'
  | 'SCHEMA_ERROR'
  | 'RATE_LIMITED'
  | 'UPSTREAM_FAILURE'
  | 'TIMEOUT'
  | 'UNSUPPORTED_CATEGORY'
  | 'QUOTA_EXHAUSTED'
  | 'INTERNAL_ERROR'

export interface ApiError {
  code: ApiErrorCode
  message: string
  retryAfter?: number
}

export interface ApiErrorResponse {
  error: ApiError
}

// ─── Health ───────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: 'ok'
  version: string
  mockMode?: boolean
}
