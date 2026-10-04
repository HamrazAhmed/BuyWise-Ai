/**
 * lib/api.ts
 * API client for BuyWise AI.
 *
 * Mock mode: set NEXT_PUBLIC_USE_MOCKS=true (explicit opt-in) to use local mock data.
 * Live mode: set NEXT_PUBLIC_USE_MOCKS=false and NEXT_PUBLIC_API_URL=<backend URL>.
 *
 * The UI remains fully functional in mock mode so it can be developed and
 * demoed without a running backend.
 */

import type {
  AnalyzeRequirementsRequest,
  AnalyzeRequirementsResponse,
  CompareProductsRequest,
  Comparison,
  FollowUpRequest,
  FollowUpResponse,
  HealthResponse,
  Product,
  ResearchProductsRequest,
  ResearchProductsResponse,
} from './types'

import { mapAnalysis, mapComparison, mapFollowUp, mapHealth, mapProduct, mapResearch } from './api-contract'
import type { WireAnalysis, WireComparison, WireError, WireFollowUp, WireProduct, WireResearch } from './api-contract'

// ─── Config ──────────────────────────────────────────────────────────────────

const USE_MOCKS =
  process.env.NEXT_PUBLIC_USE_MOCKS === undefined
    ? false
    : process.env.NEXT_PUBLIC_USE_MOCKS !== 'false'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ─── HTTP helpers ─────────────────────────────────────────────────────────────

class ApiClientError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly retryAfter?: number,
  ) {
    super(message)
    this.name = 'ApiClientError'
  }
}

async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${API_BASE}${path}`
  const res = await fetch(url, {
    signal: AbortSignal.timeout(30000),
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!res.ok) {
    let body: WireError | null = null
    try {
      body = await res.json()
    } catch {
      // ignore parse errors
    }
    const err = body?.error
    throw new ApiClientError(
      err?.code ?? 'UNKNOWN',
      err?.message ?? `HTTP ${res.status}`,
      err?.retry_after ?? undefined,
    )
  }

  return res.json() as Promise<T>
}

async function apiPost<TReq, TRes>(path: string, body: TReq): Promise<TRes> {
  return apiFetch<TRes>(path, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

// ─── Mock implementations ─────────────────────────────────────────────────────

async function mockAnalyzeRequirements(
  _req: AnalyzeRequirementsRequest,
): Promise<AnalyzeRequirementsResponse> {
  const { mockAnalyzeRequirements: mock } = await import('./mock-data')
  return mock(_req.text)
}

async function mockResearchProducts(
  _req: ResearchProductsRequest,
): Promise<ResearchProductsResponse> {
  // In mock mode we return a fake comparison_id and no real SSE stream.
  return {
    comparisonId: 'cmp_demo',
    status: 'processing',
    streamUrl: '/api/stream/cmp_demo',
  }
}

async function mockGetProduct(id: string): Promise<Product> {
  const { getProduct } = await import('./mock-data')
  return getProduct(id)
}

async function mockGetComparison(_id: string): Promise<Comparison> {
  const { getComparison } = await import('./mock-data')
  return getComparison()
}

async function mockFollowUp(req: FollowUpRequest): Promise<FollowUpResponse> {
  const { askFollowUp } = await import('./mock-data')
  const result = await askFollowUp(req.question)
  return {
    answer: result.answer,
    evidenceIds: result.citations,
    requiresRerun: false,
    suggestedRequirementsPatch: [],
  }
}

async function mockHealth(): Promise<HealthResponse> {
  return { status: 'ok', version: '0.1.0-mock' }
}

// ─── Live implementations ─────────────────────────────────────────────────────

async function liveAnalyzeRequirements(
  req: AnalyzeRequirementsRequest,
): Promise<AnalyzeRequirementsResponse> {
  return mapAnalysis(await apiPost<AnalyzeRequirementsRequest, WireAnalysis>('/api/analyze-requirements', req))
}

async function liveResearchProducts(
  req: ResearchProductsRequest,
): Promise<ResearchProductsResponse> {
  return mapResearch(await apiPost('/api/research-products', { request_id: req.requestId, requirements: req.requirements, raw_text: req.rawText ?? '' }) as WireResearch)
}

async function liveGetProduct(id: string, comparisonId: string): Promise<Product> {
  return mapProduct(await apiFetch<WireProduct>(`/api/product/${encodeURIComponent(id)}?comparison_id=${encodeURIComponent(comparisonId)}`))
}

async function liveGetComparison(id: string): Promise<Comparison> {
  return mapComparison(await apiFetch<WireComparison>(`/api/comparison/${encodeURIComponent(id)}`))
}

async function liveFollowUp(req: FollowUpRequest): Promise<FollowUpResponse> {
  return mapFollowUp(await apiPost('/api/follow-up', { comparison_id: req.comparisonId, question: req.question }) as WireFollowUp)
}

async function liveHealth(): Promise<HealthResponse> {
  return mapHealth(await apiFetch<{ status: 'ok'; version: string; mock_mode: boolean }>('/api/health'))
}

// ─── Public API client ────────────────────────────────────────────────────────

export const api = {
  /**
   * Extract structured requirements from natural-language text.
   * POST /api/analyze-requirements
   */
  analyzeRequirements: USE_MOCKS ? mockAnalyzeRequirements : liveAnalyzeRequirements,

  /**
   * Kick off the research pipeline for confirmed requirements.
   * Returns a comparison_id and stream_url for SSE progress updates.
   * POST /api/research-products
   */
  researchProducts: USE_MOCKS ? mockResearchProducts : liveResearchProducts,

  /**
   * Fetch a single product's detail (specs, evidence, warranty, etc.).
   * GET /api/product/{id}
   */
  streamUrl: (path: string) => {
    if (!path.startsWith('/api/stream/') || path.includes('..') || path.includes('?') || path.includes('#')) throw new ApiClientError('INVALID_STREAM', 'Invalid research stream URL.')
    return `${API_BASE.replace(/\/$/, '')}${path}`
  },

  getProduct: (id: string, comparisonId: string) => USE_MOCKS ? mockGetProduct(id) : liveGetProduct(id, comparisonId),

  /**
   * Fetch a stored comparison result by ID.
   * GET /api/comparison/{id}
   */
  getComparison: USE_MOCKS ? mockGetComparison : liveGetComparison,

  getResearchStatus: (id: string) => apiFetch<{ status: 'queued' | 'running' | 'done' | 'error'; error?: { message: string; retry_after?: number } }>(`/api/research-status/${encodeURIComponent(id)}`),

  /**
   * Ask a follow-up question grounded in an existing comparison.
   * POST /api/follow-up
   */
  askFollowUp: (question: string, comparisonId = 'cmp_demo') =>
    (USE_MOCKS ? mockFollowUp : liveFollowUp)({ comparisonId, question }),

  /**
   * Health check.
   * GET /api/health
   */
  health: USE_MOCKS ? mockHealth : liveHealth,

  compareProducts: async (req: CompareProductsRequest): Promise<Comparison> => {
    if (USE_MOCKS) {
      const result = await mockGetComparison('cmp_demo')
      if (req.productIds.length < 2 || req.productIds.length > 5 || new Set(req.productIds).size !== req.productIds.length) {
        throw new ApiClientError('INVALID_INPUT', 'Select 2–5 unique products.')
      }
      if (req.productIds.some(id => !result.products.some(p => p.id === id))) {
        throw new ApiClientError('NOT_FOUND', 'Selected product was not found.')
      }
      return { ...result, products: req.productIds.map(id => result.products.find(p => p.id === id)!),
        requirementMatches: Object.fromEntries(req.productIds.map(id => [id, result.requirementMatches[id]])),
        tradeoffs: [], dataMode: 'demo', notices: ['Static UI demo; use backend comparison for calculated trade-offs.'] }
    }
    return mapComparison(await apiPost('/api/compare-products', {
      request_id: req.requestId, product_ids: req.productIds, comparison_id: req.comparisonId,
    }) as WireComparison)
  },

  /** Whether the client is running in mock mode. */
  isMockMode: USE_MOCKS,
} as const

export type ApiClient = typeof api
export { ApiClientError }
export default api
