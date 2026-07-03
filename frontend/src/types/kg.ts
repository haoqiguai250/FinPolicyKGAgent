// KG 图谱相关类型定义

export interface KGNode {
  id: string
  name: string
  type: string  // Policy / Condition / ActionType / Strategy / Company
  properties?: {
    confidence?: number
    source_text?: string
    // P3 新增 — 时序化字段（Policy 节点专用）
    status?: string | null             // "active" | "repealed" | null
    effective_date?: string | null     // ISO 日期
    expiry_date?: string | null       // ISO 日期
    repealed_at?: string | null       // 废止日期
    repealed_by?: string | null       // 废止该政策的新政策名
    [key: string]: unknown
  }
}

export interface KGEdge {
  id: string
  source: string  // node id
  target: string  // node id
  relation: string
  source_chunk_id?: string
  properties?: {
    confidence?: number
    source_text?: string
    // P0 新增 — 弱归一双写
    raw_relation?: string    // 原始关系名（弱归一时有值，如 "补贴"）
    source?: string          // "extraction" | "normalized" | "auto_promoted" | "pool_backfill" | "truncated"
    // P3 新增 — 时序化
    effective_date?: string | null
    expiry_date?: string | null
    [key: string]: unknown
  }
}

export interface GraphData {
  nodes: KGNode[]
  edges: KGEdge[]
}

export interface KGStats {
  total_entities: number
  total_triples: number
  entity_type_distribution: Record<string, number>
  relation_type_distribution: Record<string, number>
  // P2 新增 — 候选池统计
  candidate_relation_count?: number
  promoted_relation_count?: number
  // P3 新增 — 时序化统计
  active_policy_count?: number
  repealed_policy_count?: number
}
