/** Validate API translations using actual Python model JSON; no network or keys. */
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { createRequire } from 'node:module'
const root = resolve(import.meta.dirname, '..')
const output = mkdtempSync(join(tmpdir(), 'buywise-contract-'))
try {
  execFileSync(join(root, 'node_modules/.bin/tsc'), ['lib/api.ts', 'lib/api-contract.ts',
    '--module', 'commonjs', '--target', 'ES2020', '--strict', '--skipLibCheck', '--outDir', output], { cwd: root })
  const python = `
import json, sys
sys.path.insert(0, 'backend')
from models.product import Product, Spec, PriceInfo, Warranty, ReturnPolicy, ReviewTheme, Evidence
from models.comparison import Comparison, RequirementAnalysis, ProductAssessment, FollowUpResponse
from models.request import Requirement, AnalyzeRequirementsResponse
from models.common import HealthResponse
req=Requirement(key='ram',operator='>=',value='32 GB',priority='must')
p=Product(id='p_one',name='Fixture',evidence=[Evidence(id='source_one',product_id='p_one',chunk_id='chunk_one',source_id='doc_one',origin='fixture',title='Synthetic record',source_url='https://fixtures.invalid/spec',source_type='secondary',snippet='RAM: 32 GB',fetched_at='2026-10-04T00:00:00Z',claims=[dict(key='RAM',value='32 GB')])],price_info=PriceInfo(amount=900,currency='USD',source_id='price_one',is_stale=True),
 specs=[Spec(key='RAM',value='32 GB',status='conflicting',evidence_ids=['source_one'],conflicting_values=[dict(value='16 GB',source_url='https://example.test/spec',source_type='secondary')])],
 warranty=Warranty(duration_months=12,coverage='parts',completeness='partial',source_id='warranty'),
 return_policy=ReturnPolicy(window_days=14,seller_dependent=True),
 review_themes=[ReviewTheme(theme='build',sentiment='positive',summary='Opinion')])
c=Comparison(id='cmp_one',request_id='req_one',products=[p],requirements=[req],requirement_matches={'p_one':['?']},
 requirement_analysis=[RequirementAnalysis(requirement=req,product_assessments=[ProductAssessment(product_id='p_one',match='?',explanation='Conflict',evidence_ids=['source_one'])])],data_mode='fixture',notices=['Fixture'])
a=AnalyzeRequirementsResponse(request_id='req_one',category='laptop',requirements=[req],missing_info=['Screen size?'],data_mode='demo',notices=['Example'])
f=FollowUpResponse(answer='Update budget',evidence_ids=['source_one'],requires_rerun=True,suggested_requirements_patch=[dict(key='budget',operator='<=',value='1200 USD')])
print(json.dumps({'product':p.model_dump(mode='json'),'comparison':c.model_dump(mode='json'),'analysis':a.model_dump(mode='json'),'followup':f.model_dump(mode='json'),'health':HealthResponse(mock_mode=True).model_dump(mode='json')}))
`
  const fixtures = JSON.parse(execFileSync(join(root, '.venv/bin/python'), ['-c', python], { cwd: root, encoding: 'utf8' }))
  process.env.NEXT_PUBLIC_USE_MOCKS = 'false'
  const require = createRequire(import.meta.url)
  const { api, ApiClientError } = require(join(output, 'api.js'))
  const captured = []
  globalThis.fetch = async (url, options) => {
    captured.push({ url, body: options?.body ? JSON.parse(options.body) : undefined })
    const path = new URL(url).pathname
    const payload = path === '/api/analyze-requirements' ? fixtures.analysis
      : path === '/api/research-products' ? { comparison_id: 'cmp_one', status: 'processing', stream_url: '/api/stream/cmp_one' }
      : path === '/api/follow-up' ? fixtures.followup
      : path === '/api/product/p_one' ? fixtures.product
      : path === '/api/health' ? fixtures.health : fixtures.comparison
    return { ok: true, json: async () => payload }
  }
  const a = await api.analyzeRequirements({ text: 'A laptop for school' })
  assert.equal(a.requestId, 'req_one'); assert.deepEqual(a.missingInfo, ['Screen size?'])
  assert.equal(a.requirements[0].priority, 'must'); assert.equal(a.dataMode, 'demo')
  const r = await api.researchProducts({ requestId: a.requestId, requirements: a.requirements, rawText: 'Original request' })
  assert.equal(r.comparisonId, 'cmp_one'); assert.equal(r.streamUrl, '/api/stream/cmp_one')
  assert.equal(captured.at(-1).body.request_id, 'req_one'); assert.equal(captured.at(-1).body.raw_text, 'Original request')
  assert.equal(captured.at(-1).body.requestId, undefined)
  const c = await api.getComparison(r.comparisonId)
  assert.equal(c.dataMode, 'fixture')
  assert.deepEqual(Object.keys(c.requirementMatches), ['p_one']) // IDs must not be converted.
  assert.equal(c.requirementAnalysis[0].productAssessments[0].productId, 'p_one')
  assert.deepEqual(c.requirementAnalysis[0].productAssessments[0].evidenceIds, ['source_one'])
  const p = await api.getProduct('p_one')
  assert.equal(p.price, null); assert.equal(p.priceInfo.amount, 900); assert.equal(p.priceInfo.isStale, true)
  assert.equal(p.specs[0].conflictingValues[0].sourceUrl, 'https://example.test/spec')
  assert.equal(p.warranty.durationMonths, 12); assert.equal(p.returnPolicy.sellerDependent, true)
  assert.equal(p.reviewThemes[0].sentiment, 'positive')
  assert.equal(p.evidence[0].productId, 'p_one'); assert.equal(p.evidence[0].sourceId, 'doc_one')
  assert.equal(p.evidence[0].origin, 'fixture'); assert.equal(p.evidence[0].snippet, 'RAM: 32 GB')
  assert.deepEqual(p.evidence[0].claims, [{ key: 'RAM', value: '32 GB' }])
  const f = await api.askFollowUp('What if $1200?', c.id)
  assert.equal(captured.at(-1).body.comparison_id, 'cmp_one')
  assert.equal(f.requiresRerun, true); assert.deepEqual(f.evidenceIds, ['source_one'])
  assert.equal(f.suggestedRequirementsPatch[0].value, '1200 USD')
  await api.compareProducts({ requestId: 'req_one', productIds: ['p_one', 'p_two'], comparisonId: 'cmp_one' })
  assert.deepEqual(captured.at(-1).body, { request_id: 'req_one', product_ids: ['p_one', 'p_two'], comparison_id: 'cmp_one' })
  assert.equal((await api.health()).mockMode, true)
  globalThis.fetch = async () => ({ ok: false, status: 429, json: async () => ({ error: { code: 'RATE_LIMITED', message: 'Wait', retry_after: 30 } }) })
  await assert.rejects(() => api.health(), e => e instanceof ApiClientError && e.code === 'RATE_LIMITED' && e.retryAfter === 30)
  console.log('PASS: API requests, nested responses, priorities, conflicts, prices, policies, citations, mode and error translation')
} finally {
  rmSync(output, { recursive: true, force: true })
}
