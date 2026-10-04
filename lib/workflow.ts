import type { AnalyzeRequirementsResponse, Requirement } from './types'
export interface ShoppingSession {
  rawText: string
  analysis?: AnalyzeRequirementsResponse
  requirements: Requirement[]
  job?: { comparisonId: string; streamUrl: string }
}
export const EMPTY_SESSION: ShoppingSession = { rawText: '', requirements: [] }
export const OPERATORS = ['<=', '<', '>=', '>', '=', '==', 'supports', 'contains']
export function validateRequirements(items: Requirement[]): string | null {
  if (items.length < 1 || items.length > 20) return 'Add between 1 and 20 requirements.'
  if (items.some(r => !r.key.trim() || r.key.length > 100 || !r.value.trim() || r.value.length > 200 || !OPERATORS.includes(r.operator))) return 'Every requirement needs a valid key, operator and value.'
  return null
}
export function applyPatches(items: Requirement[], patches: Array<Partial<Requirement>>): Requirement[] {
  const result = items.map(r => ({ ...r }))
  for (const patch of patches) {
    if (!patch.key || !patch.value || !patch.operator || !OPERATORS.includes(patch.operator)) throw new Error('The suggested requirement change is incomplete.')
    const index = result.findIndex(r => r.key.toLowerCase() === patch.key!.toLowerCase())
    const next: Requirement = { ...(index >= 0 ? result[index] : { id: crypto.randomUUID(), priority: 'must' as const }),
      key: patch.key, value: patch.value, operator: patch.operator, source: 'user', confirmed: true }
    if (index >= 0) result[index] = next
    else result.push(next)
  }
  const error = validateRequirements(result)
  if (error) throw new Error(error)
  return result
}
