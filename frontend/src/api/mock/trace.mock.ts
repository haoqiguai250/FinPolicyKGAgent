import type { TraceResult } from '../types/trace'

// Mock 追溯结果
export const mockTraceResults: TraceResult[] = [
  {
    chunk_id: 'chunk_002',
    source_file: '深圳市有力有效支持发展瞪羚企业、独角兽企业行动计划（2025—2027年）.pdf',
    paragraph_location: '第一章优化产业空间配置 第一条~第四条',
    heading: '优化产业空间配置',
    clause_range: '第一条~第四条',
    chunk_text: '第一条 优化产业空间布局，支持重点产业项目用地需求。第二条 加大产业用地供应力度，保障瞪羚企业、独角兽企业用地。第三条 支持企业通过"投贷联动"模式获得组合融资。第四条 建立科技创新专项担保计划，降低企业融资门槛。',
    section_heading: '第一章 优化产业空间配置',
    section_content: '第一章 优化产业空间配置\n\n第一条 优化产业空间布局，支持重点产业项目用地需求...\n第二条 加大产业用地供应力度...\n第三条 支持企业通过"投贷联动"模式获得组合融资...\n第四条 建立科技创新专项担保计划...',
  },
]

export async function mockTraceEntity(name: string, _type: string): Promise<TraceResult[]> {
  await new Promise(resolve => setTimeout(resolve, 600))
  return mockTraceResults.map(r => ({ ...r, chunk_text: `[追溯: ${name}] ${r.chunk_text}` }))
}
