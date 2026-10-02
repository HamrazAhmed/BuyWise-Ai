import { askFollowUp, getComparison, getEvidence, getProduct } from './mock-data'

export const api = {
  getComparison,
  getProduct,
  getEvidence,
  askFollowUp,
}

export type ApiClient = typeof api

// Replace these typed functions with fetch calls to the FastAPI service later.
export default api
