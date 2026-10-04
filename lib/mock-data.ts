/**
 * lib/mock-data.ts
 * Mock data and functions used by the API client in mock mode
 * (NEXT_PUBLIC_USE_MOCKS=true).
 *
 * Do NOT modify the UI-facing exports here (types, arrays, constants)
 * without also updating lib/types.ts and lib/api.ts accordingly.
 */

import type {
  AnalyzeRequirementsResponse,
  Comparison,
  EvidenceStatus,
  Requirement,
  Spec,
  Product,
  Evidence,
} from './types'

// Re-export UI-specific types that page.tsx still imports from here.
export type { EvidenceStatus }
export type Priority = 'Must Have' | 'High Priority' | 'Preferred' | 'Optional'

// UI Requirement type used by the existing components (different from API Requirement)
export type UIRequirement = {
  key: string
  operator: string
  value: string
  priority: Priority
  source: 'user' | 'inferred'
}

// Keep the old Requirement name exported so existing page.tsx imports don't break
export type { UIRequirement as Requirement }

// ─── Static mock data ────────────────────────────────────────────────────────

export const requirements: UIRequirement[] = [
  { key: 'Category',           operator: 'is',          value: 'Laptop',                    priority: 'Must Have',    source: 'user' },
  { key: 'Budget',             operator: '≤',            value: '$1,000',                    priority: 'Must Have',    source: 'user' },
  { key: 'RAM',                operator: '≥',            value: '32GB',                      priority: 'Must Have',    source: 'user' },
  { key: 'Virtualization',     operator: 'supports',    value: 'Multiple VMs',              priority: 'High Priority', source: 'user' },
  { key: 'Linux compatibility',operator: 'works with',  value: 'Linux',                     priority: 'High Priority', source: 'user' },
  { key: 'Upgradeability',     operator: 'should have', value: 'Accessible RAM / storage',  priority: 'Preferred',    source: 'inferred' },
]

export const evidence: Evidence[] = [
  {
    id: 'ev-1',
    title: 'Manufacturer specification sheet',
    sourceUrl: 'https://example.com/specs',
    sourceType: 'primary',
    snippet: '32GB DDR5 memory and two accessible SODIMM slots.',
    fetchedAt: 'Oct 2, 2026',
  },
  {
    id: 'ev-2',
    title: 'Independent lab review',
    sourceUrl: 'https://example.com/review',
    sourceType: 'secondary',
    snippet: 'Strong sustained performance under virtual machine workloads.',
    fetchedAt: 'Oct 2, 2026',
  },
  {
    id: 'ev-3',
    title: 'Linux hardware report',
    sourceUrl: 'https://example.com/linux',
    sourceType: 'secondary',
    snippet: 'Wi-Fi, suspend, and graphics tested on a current Linux kernel.',
    fetchedAt: 'Oct 2, 2026',
  },
  {
    id: 'ev-4',
    title: 'Retailer listing',
    sourceUrl: 'https://example.com/listing',
    sourceType: 'secondary',
    snippet: 'Listing reports a 56Wh battery; manufacturer sheet reports 54Wh.',
    fetchedAt: 'Oct 2, 2026',
  },
]

const atlasSpecs: Spec[] = [
  'CPU|Ryzen 7 7840U|verified|ev-1',
  'GPU|Radeon 780M|supported|ev-2',
  'RAM|32GB DDR5|verified|ev-1',
  'Storage|1TB NVMe|verified|ev-1',
  'Display|14" 2560×1600|verified|ev-1',
  'Battery|54–56Wh|conflicting|ev-4',
  'Weight|3.1 lb|supported|ev-2',
  'OS/Linux support|Strong|supported|ev-3',
  'Upgradeability|RAM + SSD|verified|ev-1',
  'Warranty|1 year limited|verified|ev-1',
  'Return policy|Seller-dependent|insufficient|',
  'Price|$899|supported|ev-4',
].map((s) => {
  const [key, value, status, ev] = s.split('|')
  return { key, value, status: status as EvidenceStatus, evidenceIds: ev ? [ev] : [] }
})

export const products: Product[] = [
  {
    id: 'atlas-14',
    name: 'Atlas 14 Pro',
    price: 899,
    score: '5 of 6 requirements met',
    image: 'AT',
    pros: ['32GB RAM standard', 'Excellent Linux support', 'Two upgradeable slots'],
    limitations: ['Battery evidence conflicts', 'Display is 60Hz'],
    specs: atlasSpecs,
  },
  {
    id: 'northstar-15',
    name: 'Northstar 15',
    price: 999,
    score: '4 of 6 requirements met',
    image: 'NS',
    pros: ['Powerful multi-core CPU', 'Large 15-inch workspace', 'Quiet under light use'],
    limitations: ['Linux fingerprint is mixed', 'Memory configuration varies'],
    specs: [],
  },
  {
    id: 'fieldbook-x',
    name: 'Fieldbook X',
    price: 749,
    score: '4 of 6 requirements met',
    image: 'FX',
    pros: ['Lowest listed price', 'Easy to service', 'Good keyboard'],
    limitations: ['16GB base configuration', 'Weaker integrated graphics'],
    specs: [],
  },
]

export const specRows = [
  'CPU', 'GPU', 'RAM', 'Storage', 'Display', 'Battery',
  'Weight', 'OS/Linux support', 'Upgradeability', 'Warranty', 'Return policy', 'Price',
]

export const progressSteps = [
  'Understanding requirements',
  'Finding products',
  'Verifying specifications',
  'Analyzing reviews',
  'Checking warranty & returns',
  'Verifying evidence',
]

export const chatSuggestions = [
  'Which one is better for Linux?',
  'What if I increase my budget to $1,200?',
  'Why did you mark this product as weak for virtualization?',
]

export const reviewThemes = [
  'Performance', 'Battery', 'Thermals', 'Build quality',
  'Keyboard', 'Noise', 'Common complaints', 'Common positives',
]

export const requirementsByProduct: Record<string, string[]> = {
  'atlas-14':    ['✓', '✓', '✓', '✓', '✓', '?'],
  'northstar-15':['✓', '✓', '✓', '?', '?', '✓'],
  'fieldbook-x': ['✓', '✓', '✕', '✓', '✓', '✓'],
}

export const statusLabels: Record<EvidenceStatus, string> = {
  verified:     'Verified',
  supported:    'Supported',
  conflicting:  'Conflicting',
  insufficient: 'Insufficient evidence',
}

export const priorityOptions: Priority[] = ['Must Have', 'High Priority', 'Preferred', 'Optional']

export const heroExample =
  'I need a laptop in Pakistan under 300,000 PKR for programming, with at least 16 GB RAM.'

export const footerNote =
  'Prices and availability change. Verify final retailer terms before purchase.'

export const navItems = [{ label: 'How it works', href: '#how-it-works' }]

export const clarificationQuestions = [
  'Is a 14-inch screen comfortable for your daily work?',
  'Would you consider refurbished inventory to stretch the budget?',
]

// ─── Mock API functions ───────────────────────────────────────────────────────

/** Used by api.ts in mock mode for GET /api/product/{id}. */
export function getProduct(id: string): Product {
  return products.find((p) => p.id === id) ?? products[0]
}

/** Used by api.ts in mock mode for evidence lookups. */
export function getEvidence(id: string): Evidence {
  return evidence.find((e) => e.id === id) ?? evidence[0]
}

/** Used by api.ts in mock mode for GET /api/comparison/{id}. */
export function getComparison(): Comparison {
  return {
    id: 'cmp_demo',
    requestId: 'req_demo',
    createdAt: new Date().toISOString(),
    products: products.map(p => ({ ...p, evidence: evidence.filter(e => p.specs.some(s => s.evidenceIds.includes(e.id))).map(e => ({ ...e, productId: p.id, origin: 'fixture' as const })) })),
    requirements: [{ key: 'category', operator: '=', value: 'Laptop', priority: 'must', source: 'user' }, ...mockAnalyzeRequirements('Example').requirements.slice(0, 2), mockAnalyzeRequirements('Example').requirements[3], mockAnalyzeRequirements('Example').requirements[2], mockAnalyzeRequirements('Example').requirements[4]],
    dataMode: 'demo',
    notices: ['Static illustration only: products, requirements, evidence and prices are demo data. No research was performed.'],
    requirementMatches: requirementsByProduct as Record<string, Array<'✓' | '✕' | '?'>>,
    tradeoffs: [
      'Atlas 14 satisfies virtualization through its 8-core processor and verified 32GB memory.',
      'Northstar offers more screen area, but Linux compatibility has less supporting evidence.',
      'Fieldbook keeps the budget lower but misses the 32GB must-have in its base configuration.',
    ],
  }
}

/** Used by api.ts in mock mode for POST /api/follow-up. */
export async function askFollowUp(question: string): Promise<{ answer: string; citations: string[] }> {
  return {
    answer: `Based on the available evidence, ${question.toLowerCase()} is most closely supported by Atlas 14 Pro. See the cited manufacturer and review sources before deciding.`,
    citations: ['ev-1', 'ev-2'],
  }
}

/**
 * Used by api.ts in mock mode for POST /api/analyze-requirements.
 * Always returns the demo requirements regardless of input text,
 * to simulate the Requirement Analysis Agent.
 */
export function mockAnalyzeRequirements(_text: string): AnalyzeRequirementsResponse {
  return {
    requestId: 'req_demo',
    category: 'laptop',
    requirements: [
      { key: 'budget',           operator: '<=',       value: '1000 USD', priority: 'must',      source: 'user' },
      { key: 'ram',              operator: '>=',       value: '32 GB',    priority: 'must',      source: 'user' },
      { key: 'os_compatibility', operator: '=',        value: 'Linux',    priority: 'high',      source: 'user' },
      { key: 'virtualization',   operator: '=',        value: 'high',     priority: 'high',      source: 'user' },
      { key: 'upgradeability',   operator: '=',        value: 'preferred',priority: 'preferred', source: 'inferred' },
    ],
    dataMode: 'demo',
    notices: ['Example criteria only; these were not extracted from your request.'],
    missingInfo: ['Preferred screen size?', 'Portability importance?'],
  }
}

// Legacy export kept for backward compatibility with the existing page.tsx import.
export const api = { getComparison, getProduct, getEvidence, askFollowUp }
