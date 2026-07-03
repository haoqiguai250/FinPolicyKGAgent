import type { AdvisorResult, OpportunitiesResponse, MaterialsResponse, CalendarResponse, ScheduleResponse, EnterprisesResponse, DocumentsResponse, SubmissionPackage, TrackingHistoryResponse } from '../types/advisor'
import type { MaterialItem } from '../types/advisor'
import { mockAdvise } from './mock/advisor.mock'
import { queryCache } from '../utils/async'

// 开发环境通过 .env 文件或 VITE_USE_MOCK 环境变量控制
const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

export async function advise(query: string, useCache: boolean = true): Promise<AdvisorResult> {
  if (USE_MOCK) {
    return mockAdvise(query)
  }

  // 检查缓存
  if (useCache) {
    const cached = queryCache.get(query)
    if (cached) {
      return cached
    }
  }

  // 真实 API 调用
  const { default: client } = await import('./client')
  const result = await client.post('/advise', { query })

  // 存入缓存
  queryCache.set(query, result)

  return result
}

/**
 * 获取申报机会列表（模块 C 企业申报工作台专用）
 */
export async function fetchOpportunities(query: string): Promise<OpportunitiesResponse> {
  if (USE_MOCK) {
    // 返回模拟数据
    return {
      total: 2,
      eligible_count: 1,
      ineligible_count: 1,
      missing_fields: ['员工人数'],
      opportunities: [
        {
          opportunity_id: 'abc123',
          policy_name: '深圳市科技创新扶持政策',
          policy_id: '深圳市科技创新扶持政策',
          enterprise_id: '',
          is_eligible: true,
          eligibility_checks: [
            { condition_text: '深圳注册企业', status: 'pass', is_hard: true, reason: '企业注册地在深圳' },
            { condition_text: '高新技术企业', status: 'pass', is_hard: true, reason: '企业已获高新技术企业认定' },
          ],
          hard_pass_count: 2,
          hard_fail_count: 0,
          soft_pass_count: 0,
          unknown_count: 0,
          required_materials: ['营业执照', '高新证书', '审计报告'],
          application_steps: ['网上申报', '材料提交', '专家评审', '公示'],
          deadline: '2026-06-30',
          platform_url: 'https://stic.sz.gov.cn',
          platform_name: '深圳市科技创新服务平台',
          source_department: '深圳市科技创新委员会',
          estimated_amount: '最高500万元',
          match_explanation: '企业符合深圳高新企业认定条件',
          suggestions: '建议尽快准备审计报告',
          status: 'discovered',
          created_at: '2026-05-24',
          days_until_deadline: 37,
          deadline_urgency: 'low',
        },
        {
          opportunity_id: 'def456',
          policy_name: '中小企业数字化转型补贴',
          policy_id: '中小企业数字化转型补贴',
          enterprise_id: '',
          is_eligible: false,
          eligibility_checks: [
            { condition_text: '中小微企业', status: 'pass', is_hard: true, reason: '企业属于中小微' },
            { condition_text: '成立3年以上', status: 'fail', is_hard: true, reason: '企业成立仅2年' },
          ],
          hard_pass_count: 1,
          hard_fail_count: 1,
          soft_pass_count: 0,
          unknown_count: 0,
          required_materials: [],
          application_steps: [],
          deadline: '',
          platform_url: '',
          platform_name: '',
          source_department: '',
          estimated_amount: '',
          match_explanation: '',
          suggestions: '',
          status: 'discovered',
          created_at: '2026-05-24',
          days_until_deadline: null,
          deadline_urgency: null,
        },
      ],
    }
  }

  const { default: client } = await import('./client')
  const params: Record<string, string> = {}
  // 从 localStorage 读取 enterprise_id，传给后端跳过 LLM 意图识别
  const eid = localStorage.getItem('profile_enterprise_id')
  if (eid) params.enterprise_id = eid
  return client.post('/advise/opportunities', { query }, { params })
}

// 清除查询缓存
export function clearAdvisorCache(): void {
  queryCache.clear()
}

// 删除指定查询的缓存
export function removeAdvisorCache(query: string): void {
  queryCache.remove(query)
}

// ── Phase 3: 企业 + 机会 + 材料 + 日历 ──

/** 获取企业列表 */
export async function fetchEnterprises(): Promise<EnterprisesResponse> {
  const { default: client } = await import('./client')
  return client.get('/enterprises')
}

/** 注册企业 */
export async function createEnterprise(name: string, profile?: Record<string, unknown>): Promise<Record<string, unknown>> {
  const { default: client } = await import('./client')
  return client.post('/enterprises', { name, profile: profile || {} })
}

/** 获取申报机会列表（从 DB，带持久化） */
export async function fetchPersistedOpportunities(enterpriseId: string, status?: string): Promise<Record<string, unknown>> {
  const { default: client } = await import('./client')
  const params: Record<string, string> = { enterprise_id: enterpriseId }
  if (status) params.status = status
  return client.get('/opportunities', { params })
}

/** 推进申报状态 */
export async function updateOpportunityStatus(opportunityId: string, newStatus: string, note?: string): Promise<Record<string, unknown>> {
  const { default: client } = await import('./client')
  return client.patch(`/opportunities/${opportunityId}/status`, { new_status: newStatus, note: note || '' })
}

/** 获取操作时间线 */
export async function fetchOpportunityTimeline(opportunityId: string): Promise<Record<string, unknown>> {
  const { default: client } = await import('./client')
  return client.get(`/opportunities/${opportunityId}/timeline`)
}

/** 重新核验 */
export async function refreshOpportunity(opportunityId: string): Promise<Record<string, unknown>> {
  const { default: client } = await import('./client')
  return client.post(`/opportunities/${opportunityId}/refresh`)
}

/** 获取材料清单 */
export async function fetchMaterials(opportunityId: string): Promise<MaterialsResponse> {
  const { default: client } = await import('./client')
  return client.get(`/opportunities/${opportunityId}/materials`)
}

/** 更新材料状态 */
export async function updateMaterial(materialId: string, status?: string, notes?: string): Promise<MaterialItem> {
  const { default: client } = await import('./client')
  return client.patch(`/materials/${materialId}`, { status, notes })
}

/** LLM 生成材料清单 */
export async function generateMaterials(opportunityId: string): Promise<Record<string, unknown>> {
  const { default: client } = await import('./client')
  return client.post(`/opportunities/${opportunityId}/materials/generate`, {})
}

/** 获取日历数据 */
export async function fetchCalendar(enterpriseId: string, month?: string): Promise<CalendarResponse> {
  const { default: client } = await import('./client')
  const params: Record<string, string> = { enterprise_id: enterpriseId }
  if (month) params.month = month
  return client.get('/calendar', { params })
}

/** 获取推荐排期 */
export async function fetchSchedule(enterpriseId: string): Promise<ScheduleResponse> {
  const { default: client } = await import('./client')
  return client.get(`/enterprises/${enterpriseId}/schedule`)
}

/** 重核验企业所有机会 */
export async function recheckEnterprise(enterpriseId: string): Promise<Record<string, unknown>> {
  const { default: client } = await import('./client')
  return client.post(`/enterprises/${enterpriseId}/recheck`)
}

/** 获取企业画像 */
export async function fetchEnterpriseProfile(enterpriseId: string): Promise<Record<string, unknown>> {
  const { default: client } = await import('./client')
  return client.get(`/enterprises/${enterpriseId}/profile`)
}

/** 保存企业画像 */
export async function saveEnterpriseProfile(enterpriseId: string, profile: Record<string, unknown>): Promise<Record<string, unknown>> {
  const { default: client } = await import('./client')
  return client.put(`/enterprises/${enterpriseId}/profile`, profile)
}

/** NLU 快速导入企业画像 */
export async function nluEnterpriseProfile(enterpriseId: string, text: string): Promise<Record<string, unknown>> {
  const { default: client } = await import('./client')
  return client.post(`/enterprises/${enterpriseId}/profile/nlu`, { text })
}

// ── 文档生成 ──

/** 生成申报文档 */
export async function generateDocuments(opportunityId: string, docType: string = 'docx'): Promise<Record<string, unknown>> {
  const { default: client } = await import('./client')
  return client.post(`/opportunities/${opportunityId}/documents/generate`, { doc_type: docType })
}

/** 获取已生成文档列表 */
export async function fetchDocuments(opportunityId: string): Promise<DocumentsResponse> {
  const { default: client } = await import('./client')
  return client.get(`/opportunities/${opportunityId}/documents`)
}

/** 获取文档下载 URL */
export function getDocumentDownloadUrl(docId: string): string {
  const base = (import.meta.env.VITE_API_BASE as string) || '/api'
  return `${base}/documents/${docId}/download`
}

/** 删除文档 */
export async function deleteDocument(docId: string): Promise<void> {
  const { default: client } = await import('./client')
  return client.delete(`/documents/${docId}`)
}

// ── 申报提交 ──

/** 准备申报包 */
export async function prepareSubmission(opportunityId: string): Promise<SubmissionPackage> {
  const { default: client } = await import('./client')
  return client.post(`/opportunities/${opportunityId}/submission/prepare`)
}

/** 确认提交 */
export async function confirmSubmission(opportunityId: string, confirmedBy: string = 'user'): Promise<Record<string, unknown>> {
  const { default: client } = await import('./client')
  return client.post(`/opportunities/${opportunityId}/submission/confirm`, { confirmed_by: confirmedBy })
}

/** 获取申报包 */
export async function fetchSubmissionPackage(opportunityId: string): Promise<SubmissionPackage> {
  const { default: client } = await import('./client')
  return client.get(`/opportunities/${opportunityId}/submission`)
}

// ── 进度追踪 ──

/** 检查申报状态 */
export async function checkOpportunityStatus(opportunityId: string): Promise<Record<string, unknown>> {
  const { default: client } = await import('./client')
  return client.post(`/opportunities/${opportunityId}/tracking/check`)
}

/** 获取追踪历史 */
export async function fetchTrackingHistory(opportunityId: string): Promise<TrackingHistoryResponse> {
  const { default: client } = await import('./client')
  return client.get(`/opportunities/${opportunityId}/tracking/history`)
}

/** 手动更新状态 */
export async function manualStatusUpdate(opportunityId: string, newStatus: string, note: string): Promise<Record<string, unknown>> {
  const { default: client } = await import('./client')
  return client.post(`/opportunities/${opportunityId}/tracking/update`, { new_status: newStatus, note })
}
