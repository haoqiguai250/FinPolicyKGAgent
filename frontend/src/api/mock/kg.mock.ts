import type { KGStats, GraphData } from '../types/kg'

// Mock KG 统计数据
export const mockKGStats: KGStats = {
  total_entities: 156,
  total_triples: 234,
  entity_type_distribution: {
    Policy: 8,
    Condition: 42,
    ActionType: 6,
    Strategy: 8,
    Company: 2,
    Region: 12,
  },
  relation_type_distribution: {
    has_eligibility: 56,
    provides: 24,
    leads_to: 18,
    targets: 32,
    subregion_of: 11,
    references: 93,
  },
}

// Mock 图谱数据（用于 D3.js 力导向图）
export const mockGraphData: GraphData = {
  nodes: [
    { id: 'p1', name: '瞪羚企业行动计划', type: 'Policy' },
    { id: 'p2', name: '研发投入补助管理办法', type: 'Policy' },
    { id: 'p3', name: '坪山区支持实体经济若干措施', type: 'Policy' },
    { id: 'p4', name: '人工智能+先进制造业行动计划', type: 'Policy' },
    { id: 'c1', name: '深圳', type: 'Condition' },
    { id: 'c2', name: '中小企业', type: 'Condition' },
    { id: 'c3', name: '制造业', type: 'Condition' },
    { id: 'c4', name: '坪山区', type: 'Condition' },
    { id: 'c5', name: '重点产业项目', type: 'Condition' },
    { id: 'c6', name: '瞪羚企业', type: 'Condition' },
    { id: 'c7', name: '独角兽企业', type: 'Condition' },
    { id: 'c8', name: '研发投入', type: 'Condition' },
    { id: 'a1', name: '融资类', type: 'ActionType' },
    { id: 'a2', name: '财政类', type: 'ActionType' },
    { id: 'a3', name: '税收类', type: 'ActionType' },
    { id: 'a4', name: '风险类', type: 'ActionType' },
    { id: 'a5', name: '投资类', type: 'ActionType' },
    { id: 'a6', name: '人才类', type: 'ActionType' },
    { id: 's1', name: '扩大融资能力', type: 'Strategy' },
    { id: 's2', name: '降低成本', type: 'Strategy' },
    { id: 's3', name: '提高利润', type: 'Strategy' },
    { id: 's4', name: '降低融资门槛', type: 'Strategy' },
    { id: 's5', name: '扩张业务', type: 'Strategy' },
    { id: 's6', name: '提升能力', type: 'Strategy' },
    { id: 's7', name: '扩产', type: 'Strategy' },
    { id: 's8', name: '增加投入', type: 'Strategy' },
    { id: 'co1', name: '深圳XX制造有限公司', type: 'Company' },
  ],
  edges: [
    { id: 'e1', source: 'p1', target: 'c1', relation: 'has_eligibility' },
    { id: 'e2', source: 'p1', target: 'c6', relation: 'has_eligibility' },
    { id: 'e3', source: 'p1', target: 'c7', relation: 'has_eligibility' },
    { id: 'e4', source: 'p1', target: 'a1', relation: 'provides' },
    { id: 'e5', source: 'p1', target: 'a4', relation: 'provides' },
    { id: 'e6', source: 'p1', target: 'a6', relation: 'provides' },
    { id: 'e7', source: 'p2', target: 'c1', relation: 'has_eligibility' },
    { id: 'e8', source: 'p2', target: 'c8', relation: 'has_eligibility' },
    { id: 'e9', source: 'p2', target: 'a2', relation: 'provides' },
    { id: 'e10', source: 'p2', target: 'a3', relation: 'provides' },
    { id: 'e11', source: 'p3', target: 'c4', relation: 'has_eligibility' },
    { id: 'e12', source: 'p3', target: 'c5', relation: 'has_eligibility' },
    { id: 'e13', source: 'p3', target: 'a2', relation: 'provides' },
    { id: 'e14', source: 'p4', target: 'c1', relation: 'has_eligibility' },
    { id: 'e15', source: 'p4', target: 'c3', relation: 'has_eligibility' },
    { id: 'e16', source: 'p4', target: 'a5', relation: 'provides' },
    { id: 'e17', source: 'a1', target: 's1', relation: 'leads_to' },
    { id: 'e18', source: 'a1', target: 's7', relation: 'leads_to' },
    { id: 'e19', source: 'a2', target: 's2', relation: 'leads_to' },
    { id: 'e20', source: 'a2', target: 's8', relation: 'leads_to' },
    { id: 'e21', source: 'a3', target: 's3', relation: 'leads_to' },
    { id: 'e22', source: 'a4', target: 's4', relation: 'leads_to' },
    { id: 'e23', source: 'a5', target: 's5', relation: 'leads_to' },
    { id: 'e24', source: 'a6', target: 's6', relation: 'leads_to' },
    { id: 'e25', source: 'co1', target: 'c1', relation: 'has' },
    { id: 'e26', source: 'co1', target: 'c2', relation: 'has' },
    { id: 'e27', source: 'co1', target: 'c3', relation: 'has' },
  ],
}

// 模拟加载（带延迟）
export async function mockLoadKGStats(): Promise<KGStats> {
  await new Promise(resolve => setTimeout(resolve, 800))
  return mockKGStats
}

export async function mockLoadGraphData(): Promise<GraphData> {
  await new Promise(resolve => setTimeout(resolve, 1200))
  return mockGraphData
}
