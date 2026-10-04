/** Explicit translation between the snake_case API and camelCase UI models. */
import type { AnalyzeRequirementsResponse, Comparison, EvidenceStatus, FollowUpResponse,
  HealthResponse, Product, Requirement, RequirementAnalysis, ResearchProductsResponse,
  ReviewTheme, Warranty, ReturnPolicy, PriceInfo } from './types'

export interface WireSpec {
  key: string; value: string; status: EvidenceStatus; evidence_ids: string[]
  conflicting_values?: Array<{ value: string; source_url: string; source_type: 'primary' | 'secondary' }>
}
export interface WireEvidence {
  id: string; product_id: string | null; chunk_id: string | null; source_id: string | null
  origin: 'web' | 'curated' | 'fixture' | 'search'; kind: string; title: string; source_url: string
  source_type: 'primary' | 'secondary'; snippet: string; fetched_at: string
  claims: Array<{ key: string; value: string }>
}
export interface WireProduct {
  evidence?: WireEvidence[]
  id: string; name: string; brand: string | null; category: string | null
  model_number: string | null; canonical_url: string | null
  score: string; image: string; pros: string[]; limitations: string[]; specs: WireSpec[]
  price_info: { amount: number | null; currency: string; seller: string | null;
    fetched_at: string | null; is_stale: boolean; source_id: string | null } | null
  review_themes: Array<{ theme: string; sentiment: ReviewTheme['sentiment']; summary: string; source_id: string | null }>
  warranty: { duration_months: number | null; coverage: string | null; conditions: string | null;
    completeness: Warranty['completeness']; source_id: string | null } | null
  return_policy: { window_days: number | null; conditions: string | null;
    seller_dependent: boolean; source_id: string | null } | null
  must_have_status: 'met' | 'not_met' | 'uncertain'; weighted_match_score: number
}
export interface WireComparison {
  id: string; request_id: string; created_at: string; products: WireProduct[]
  requirements: Requirement[]; requirement_matches: Comparison['requirementMatches']; tradeoffs: string[]
  requirement_analysis: Array<{ requirement: Requirement; product_assessments: Array<{
    product_id: string; match: '✓' | '✕' | '?'; explanation: string; evidence_ids: string[] }> }>
  data_mode: 'live' | 'demo' | 'fixture'; notices: string[]
  search_report?: Comparison['searchReport'] | null
}
export interface WireAnalysis {
  request_id: string; category: string; requirements: Requirement[]; missing_info: string[]
  data_mode: 'live' | 'demo' | 'fixture'; notices: string[]
}
export interface WireFollowUp {
  answer: string; evidence_ids: string[]; requires_rerun: boolean; suggested_requirements_patch: Array<Partial<Requirement>>
}
export interface WireResearch { comparison_id: string; status: 'processing'; stream_url: string }
export interface WireError { error: { code: string; message: string; retry_after?: number | null } }

export function mapProduct(p: WireProduct): Product {
  const info: PriceInfo | null = p.price_info ? {
    amount: p.price_info.amount, currency: p.price_info.currency, seller: p.price_info.seller,
    fetchedAt: p.price_info.fetched_at, isStale: p.price_info.is_stale, sourceId: p.price_info.source_id ?? undefined,
  } : null
  const warranty: Warranty | null = p.warranty ? { durationMonths: p.warranty.duration_months,
    coverage: p.warranty.coverage, conditions: p.warranty.conditions,
    completeness: p.warranty.completeness, sourceId: p.warranty.source_id ?? undefined } : null
  const returnPolicy: ReturnPolicy | null = p.return_policy ? { windowDays: p.return_policy.window_days,
    conditions: p.return_policy.conditions, sellerDependent: p.return_policy.seller_dependent,
    sourceId: p.return_policy.source_id ?? undefined } : null
  return { id: p.id, name: p.name, brand: p.brand ?? undefined, category: p.category ?? undefined,
    modelNumber: p.model_number ?? undefined, canonicalUrl: p.canonical_url ?? undefined,
    price: info?.isStale ? null : info?.amount ?? null, priceFetchedAt: info?.fetchedAt ?? null,
    priceSeller: info?.seller ?? null, priceInfo: info, warranty, returnPolicy,
    evidence: (p.evidence ?? []).map(e => ({ id: e.id, productId: e.product_id ?? undefined,
      chunkId: e.chunk_id ?? undefined, sourceId: e.source_id ?? undefined, origin: e.origin, kind: e.kind,
      title: e.title, sourceUrl: e.source_url, sourceType: e.source_type, snippet: e.snippet,
      fetchedAt: e.fetched_at, claims: e.claims })),
    score: p.score, image: p.image, pros: p.pros, limitations: p.limitations,
    mustHaveStatus: p.must_have_status, weightedMatchScore: p.weighted_match_score,
    reviewThemes: p.review_themes.map(r => ({ theme: r.theme, sentiment: r.sentiment,
      summary: r.summary, sourceId: r.source_id ?? undefined })),
    specs: p.specs.map(s => ({ key: s.key, value: s.value, status: s.status, evidenceIds: s.evidence_ids,
      conflictingValues: s.conflicting_values?.map(c => ({ value: c.value, sourceUrl: c.source_url, sourceType: c.source_type })) })),
  }
}
export function mapComparison(c: WireComparison): Comparison {
  const requirementAnalysis: RequirementAnalysis[] = c.requirement_analysis.map(a => ({ requirement: a.requirement,
    productAssessments: a.product_assessments.map(p => ({ productId: p.product_id, match: p.match,
      explanation: p.explanation, evidenceIds: p.evidence_ids })) }))
  return { id: c.id, requestId: c.request_id, createdAt: c.created_at, products: c.products.map(mapProduct),
    requirements: c.requirements, requirementMatches: c.requirement_matches, tradeoffs: c.tradeoffs,
    requirementAnalysis, dataMode: c.data_mode, notices: c.notices, searchReport: c.search_report ?? undefined }
}
export function mapAnalysis(a: WireAnalysis): AnalyzeRequirementsResponse {
  return { requestId: a.request_id, category: a.category, requirements: a.requirements,
    missingInfo: a.missing_info, dataMode: a.data_mode, notices: a.notices }
}
export function mapResearch(r: WireResearch): ResearchProductsResponse {
  return { comparisonId: r.comparison_id, status: r.status, streamUrl: r.stream_url }
}
export function mapFollowUp(r: WireFollowUp): FollowUpResponse {
  return { answer: r.answer, evidenceIds: r.evidence_ids, requiresRerun: r.requires_rerun,
    suggestedRequirementsPatch: r.suggested_requirements_patch }
}
export function mapHealth(r: { status: 'ok'; version: string; mock_mode: boolean }): HealthResponse {
  return { status: r.status, version: r.version, mockMode: r.mock_mode }
}
