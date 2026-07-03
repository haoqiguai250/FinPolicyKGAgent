import type { EvaluationData } from '../types/evaluation'
import { mockLoadEvaluation } from './mock/evaluation.mock'

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

export async function fetchEvaluationData(): Promise<EvaluationData> {
  if (USE_MOCK) {
    return mockLoadEvaluation()
  }
  const { default: client } = await import('./client')
  return client.post('/evaluate')
}
