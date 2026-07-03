/** 推送管理类型定义 */

/** 企业画像（完整15字段，与后端 EnterpriseProfileRequest 对齐） */
export interface EnterpriseProfile {
  region: string | null
  company_type: string | null
  industry: string | null
  employees: number | null
  annual_revenue: number | null
  established_date: string | null
  is_high_tech: boolean | null
  is_sme: boolean | null
  patents: number | null
  qualifications: string[]
  registered_capital: number | null
  rd_ratio: number | null
  intent_summary: string
  target_subsidy: string | null
  extra_note: string
}

/** 推送偏好 */
export interface PushPreference {
  enabled: boolean
  deadline_remind_days: number
  remind_missing_fields: boolean
  regions: string[]
}

/** 截止日期提醒 */
export interface DeadlineReminder {
  policy_name: string
  deadline: string
  days_left: number
  urgency: 'high' | 'medium' | 'low'
  application_platform: string
  application_platform_url: string
  contact_department: string
}

/** 推送记录（来自 PushResult.to_dict()） */
export interface PushRecord {
  push_time: string
  profile: EnterpriseProfile
  query: string
  has_match: boolean
  matched_policies: string[]
  kg_rag_answer: string
  llm_direct_answer: string
  source: string
  reasoning_paths: any[]
  new_policies_count: number
  // Phase 2 模块 D
  application_plans?: any[]
  missing_fields?: string[]
  deadline_reminders?: DeadlineReminder[]
  // P3 新增 — 废止标注
  repealed_notes?: Array<{
    repealed_policy: string
    repealed_at: string
    replaced_by: string
  }>
}

/** GET /api/push/records 响应 */
export interface PushRecordsResponse {
  total: number
  records: PushRecord[]
}

/** GET /api/push/deadlines 响应 */
export interface DeadlineRemindersResponse {
  total: number
  reminders: DeadlineReminder[]
}
