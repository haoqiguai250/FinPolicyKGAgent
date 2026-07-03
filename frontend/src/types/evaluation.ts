// 评估报告相关类型定义

export interface L1Rule {
  rule: string
  description: string
  pass: boolean
  rate: number  // 0-100
  details: string
}

export interface L2Metrics {
  ecr: number  // Entity Coverage Rate
  tcr: number  // Triple Coverage Rate
  rcr: number  // Relation Coverage Rate
  doc_breakdown: Array<{
    doc_name: string
    ecr: number
    tcr: number
    rcr: number
  }>
}

export interface L3Metrics {
  shannon_entropy: number
  renyi_entropy: number
  type_distribution: Record<string, number>
  diversity_score: number  // 0-100
}

export interface L4Dimension {
  name: string
  score: number  // 0-100
  color: string
}

export interface L4Metrics {
  dimensions: L4Dimension[]
  overall_score: number  // 0-100
  llm_judge_comments: string
  doc_scores: Array<{
    doc_name: string
    precision: number
    faithfulness: number
    completeness: number
    relevance: number
  }>
}

export interface EvaluationReport {
  id: string
  doc_name: string
  timestamp: string
  l1: L1Metrics
  l2: L2Metrics
  l3: L3Metrics
  l4: L4Metrics
}

export interface L1Metrics {
  overall_rate: number
  rules: L1Rule[]
}

export interface EvaluationData {
  reports: EvaluationReport[]
  summary: {
    total_docs: number
    avg_l1: number
    avg_l2: number
    avg_l3: number
    avg_l4: number
  }
}
