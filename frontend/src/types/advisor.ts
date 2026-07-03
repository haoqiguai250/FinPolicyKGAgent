// Advisor 相关类型定义

export interface EnterpriseProfile {
  region: string | null
  company_type: string | null
  industry: string | null
  intent_summary: string
}

export interface SubPathTriple {
  subject: string
  relation: string
  object: string
  source_chunk_id: string
  source_text: string
}

export interface ReasoningPath {
  policy: string
  conditions: Array<{
    category: string | null
    value: string
    source_chunk_id?: string
    source_text?: string
  }>
  action_type: string
  action_raw: string[]
  strategies: string[]
  sub_paths: SubPathTriple[]

  // P0 新增 — 弱归一原始关系名
  provides_raw_relation?: string        // 如 "补贴"，无归一时为 ""

  // P3 新增 — 时序化字段
  policy_status?: string | null         // "active" | "repealed" | null
  policy_expiry_date?: string | null    // ISO 日期
  policy_effective_date?: string | null // ISO 日期

  perturbation_scores?: PerturbationScore[]
}

export interface PerturbationScore {
  node: {
    name: string
    type: string
    source_chunk_id: string
    source_text: string
  }
  display: string
  importance: number
  reason: string
  metric_scores?: {
    char_overlap_diff: number
    entity_retention_diff: number
    keyword_coverage_diff: number
    llm_semantic_score: number
    weights: {
      char_overlap: number
      entity_retention: number
      keyword_coverage: number
      llm_semantic: number
    }
  }
}

export interface Explanation {
  summary: string
  key_factors: Array<{
    name: string
    type: string
    importance: number
    description: string
  }>
  detail_text: string
}

export interface AdvisorResult {
  query: string
  profile: EnterpriseProfile
  source: 'both' | 'kg_rag' | 'llm_direct'
  auto_save_path: string | null

  // ── 三次 LLM 回答 ──
  original_kg_rag_answer: string | null       // 首次 KG-RAG 回答（过滤前）
  filtered_kg_rag_answer: string | null       // 低分节点过滤后重新生成的回答
  llm_direct_answer: string | null            // 直接问 LLM 的回答

  // ── 推理子图（过滤前后完整保留） ──
  original_paths: ReasoningPath[]             // 过滤前完整子图
  filtered_paths: ReasoningPath[]             // 过滤后子图（与 original 相同时为过滤前）
  low_score_nodes: Array<{                    // 被删除的低分节点
    name: string
    type: string
  }>

  // ── 汇总统计 ──
  matched_policies: string[]
  matched_actions: string[]
  matched_strategies: string[]
  explanation: Explanation | null

  // P3 新增 — 政策状态映射
  policy_status_map?: Record<string, string>  // {"政策名": "repealed" | "active" | "expiring_soon"}
}

// 查询历史记录
export interface QueryHistory {
  id: string
  query: string
  timestamp: number
  summary: string
  result?: AdvisorResult
}

// ── Phase 2 模块 C: 企业申报工作台 ──

/** 条件核验简要信息 */
export interface EligibilityCheckBrief {
  condition_text: string
  status: 'pass' | 'fail' | 'unknown'
  is_hard: boolean
  reason: string
}

/** 申报机会 — 企业与政策之间的核心业务对象 */
export interface ApplicationOpportunity {
  opportunity_id: string
  policy_name: string
  policy_id: string
  enterprise_id: string
  is_eligible: boolean
  eligibility_checks: EligibilityCheckBrief[]
  hard_pass_count: number
  hard_fail_count: number
  soft_pass_count: number
  unknown_count: number
  required_materials: string[]
  application_steps: string[]
  deadline: string
  platform_url: string
  platform_name: string
  source_department: string
  estimated_amount: string
  match_explanation: string
  suggestions: string
  status: 'discovered' | 'applying' | 'submitted' | 'approved' | 'rejected'
  created_at: string
  days_until_deadline: number | null
  deadline_urgency: 'high' | 'medium' | 'low' | null
  effective_date: string
  expiry_date: string
  policy_status: string
}

/** 申报机会列表响应 */
export interface OpportunitiesResponse {
  total: number
  eligible_count: number
  ineligible_count: number
  missing_fields: string[]
  opportunities: ApplicationOpportunity[]
}

// ── Phase 3: 材料 + 排期 ──

/** 材料清单项 */
export interface MaterialItem {
  material_id: string
  opportunity_id: string
  material_name: string
  status: 'preparing' | 'ready' | 'submitted' | 'waived'
  notes: string
  source: 'kg' | 'llm' | 'manual'
  created_at: string
  updated_at: string
}

/** 材料完成度 */
export interface MaterialsProgress {
  total: number
  ready_count: number
  progress_pct: number
}

/** 材料清单响应 */
export interface MaterialsResponse {
  opportunity_id: string
  policy_name: string
  materials: MaterialItem[]
  progress: MaterialsProgress
}

/** 日历事件 */
export interface CalendarEvent {
  opportunity_id: string
  policy_name: string
  status: string
  is_eligible: boolean
  deadline: string
  days_left: number
  urgency: 'overdue' | 'high' | 'medium' | 'low'
}

/** 日历日数据 */
export interface CalendarDay {
  date: string
  opportunities: CalendarEvent[]
}

/** 日历响应 */
export interface CalendarResponse {
  enterprise_id: string
  month: string
  total_deadlines: number
  calendar: CalendarDay[]
}

/** 排期项 */
export interface ScheduleItem extends ApplicationOpportunity {
  schedule_score: number
  recommendation_rank: number
  recommendation_reason: string
}

/** 排期响应 */
export interface ScheduleResponse {
  enterprise_id: string
  total: number
  schedule: ScheduleItem[]
}

/** 企业信息 */
export interface Enterprise {
  enterprise_id: string
  name: string
  profile_json: string
  created_at: string
  updated_at: string
}

/** 企业列表响应 */
export interface EnterprisesResponse {
  total: number
  enterprises: Enterprise[]
}

/** 生成的文档 */
export interface GeneratedDocument {
  doc_id: string
  opportunity_id: string
  material_id: string
  doc_name: string
  doc_type: string
  file_path: string
  file_size: number
  status: string
  created_at: string
}

/** 文档列表响应 */
export interface DocumentsResponse {
  opportunity_id: string
  documents: GeneratedDocument[]
  total: number
}

/** 申报包 */
export interface SubmissionPackage {
  package_id: string
  opportunity_id: string
  status: string
  materials_checklist: unknown[]
  documents: unknown[]
  profile_snapshot: Record<string, unknown>
  policy_snapshot: Record<string, unknown>
  submission_strategy: string
  confirmed_by: string | null
  confirmed_at: string | null
  submitted_at: string | null
}

/** 追踪历史事件 */
export interface TrackingHistoryEvent {
  event_id: string
  opportunity_id: string
  event_type: string
  old_status: string | null
  new_status: string
  note: string
  created_at: string
}

/** 追踪历史响应 */
export interface TrackingHistoryResponse {
  opportunity_id: string
  events: TrackingHistoryEvent[]
  total: number
}
