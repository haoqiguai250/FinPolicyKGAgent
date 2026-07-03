import type { TraceResult } from '../types/trace'
import { mockTraceEntity } from './mock/trace.mock'

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

export async function traceEntity(name: string, type: string): Promise<TraceResult[]> {
  if (USE_MOCK) {
    return mockTraceEntity(name, type)
  }
  const { default: client } = await import('./client')
  return client.post('/trace/entity', { entity_name: name, entity_type: type })
}

export async function traceChunk(sourceFile: string, chunkId: string): Promise<TraceResult> {
  if (USE_MOCK) {
    const results = await mockTraceEntity(chunkId, '')
    return results[0]
  }
  const { default: client } = await import('./client')
  return client.post('/trace/chunk', { source_file: sourceFile, chunk_id: chunkId })
}
