import type { KGStats, GraphData } from '../types/kg'
import { mockLoadKGStats, mockLoadGraphData } from './mock/kg.mock'

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

export async function fetchKGStats(): Promise<KGStats> {
  if (USE_MOCK) {
    return mockLoadKGStats()
  }
  const { default: client } = await import('./client')
  return client.get('/kg/stats')
}

export async function fetchGraphData(): Promise<GraphData> {
  if (USE_MOCK) {
    return mockLoadGraphData()
  }
  const { default: client } = await import('./client')
  return client.get('/kg/graph')
}
