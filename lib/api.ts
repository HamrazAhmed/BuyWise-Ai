/**
 * lib/api.ts
 * API client for BuyWise AI.
 *
 * Mock mode: set NEXT_PUBLIC_USE_MOCKS=true (default) to use local mock data.
 * Live mode: set NEXT_PUBLIC_USE_MOCKS=false and NEXT_PUBLIC_API_URL=<backend URL>.
 *
 * The UI remains fully functional in mock mode so it can be developed and
 * demoed without a running backend.
 */

import type {
  AnalyzeRequirementsRequest,
  AnalyzeRequirementsResponse,
  ApiErrorResponse,
  Comparison,
  FollowUpRequest,
  FollowUpResponse,
  HealthResponse,
  Product,
  ResearchProductsRequest,
  ResearchProductsResponse,
} from './types'

// ─── Config ──────────────────────────────────────────────────────────────────

const USE_MOCKS =
  process.env.NEXT_PUBLIC_USE_MOCKS === undefined
    ? true
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
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!res.ok) {
    let body: ApiErrorResponse | null = null
    try {
      body = await res.json()
    } catch {
      // ignore parse errors
    }
    const err = body?.error
    throw new ApiClientError(
      err?.code ?? 'UNKNOWN',
      err?.message ?? `HTTP ${res.status}`,
      err?.retryAfter,
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
  return apiPost<AnalyzeRequirementsRequest, AnalyzeRequirementsResponse>(
    '/api/analyze-requirements',
    req,
  )
}

async function liveResearchProducts(
  req: ResearchProductsRequest,
): Promise<ResearchProductsResponse> {
  return apiPost<ResearchProductsRequest, ResearchProductsResponse>(
    '/api/research-products',
    req,
  )
}

async function liveGetProduct(id: string): Promise<Product> {
  return apiFetch<Product>(`/api/product/${encodeURIComponent(id)}`)
}

async function liveGetComparison(id: string): Promise<Comparison> {
  return apiFetch<Comparison>(`/api/comparison/${encodeURIComponent(id)}`)
}

async function liveFollowUp(req: FollowUpRequest): Promise<FollowUpResponse> {
  return apiPost<FollowUpRequest, FollowUpResponse>('/api/follow-up', req)
}

async function liveHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/api/health')
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
  getProduct: USE_MOCKS ? mockGetProduct : liveGetProduct,

  /**
   * Fetch a stored comparison result by ID.
   * GET /api/comparison/{id}
   */
  getComparison: USE_MOCKS ? mockGetComparison : liveGetComparison,

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

  /** Whether the client is running in mock mode. */
  isMockMode: USE_MOCKS,
} as const

export type ApiClient = typeof api
export { ApiClientError }
export default api
