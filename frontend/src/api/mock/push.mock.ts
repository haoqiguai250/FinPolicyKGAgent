import type { EnterpriseProfile, PushRecord } from '../../types/push'

/** 模拟企业画像 */
const MOCK_PROFILE: EnterpriseProfile = {
  region: '深圳市',
  company_type: '科技型中小企业',
  industry: '人工智能',
  employees: null,
  annual_revenue: null,
  established_date: null,
  is_high_tech: null,
  is_sme: null,
  patents: null,
  qualifications: [],
  registered_capital: null,
  rd_ratio: null,
  intent_summary: '',
  target_subsidy: null,
  extra_note: '',
}

/** 模拟推送记录 */
const MOCK_RECORDS: PushRecord[] = [
  {
    push_time: '2026-05-16 21:31:28',
    profile: { ...MOCK_PROFILE },
    query: '深圳市 科技型中小企业 人工智能 能享受什么政策补贴？',
    has_match: true,
    matched_policies: [
      '一次性3000万元奖励',
      '世界500强总部新设立或新迁入奖励政策',
      '深圳高新区高新技术企业培育资助',
      '深圳高新区高新区加快发展新兴产业政策',
      '深圳国家高新区坪山园区企业研发机构',
      '深圳国家高新区坪山园区科技创新平台',
      '深圳国家高新区坪山园区科技成果转化政策',
      '深圳国家高新区坪山园区产业链关键环节提升政策',
      '深圳国家高新区坪山园区创新创业团队',
      '深圳国家高新区坪山园区深港创新圈项目',
    ],
    kg_rag_answer: '',
    llm_direct_answer:
      '根据您的企业情况（深圳市、科技型中小企业、人工智能），以下是为您梳理的适用政策：\n\n'
      + '**一、资金奖励类**\n1. 一次性3000万元奖励 - 对符合条件的企业给予一次性奖励\n'
      + '2. 世界500强总部新设立或新迁入奖励政策 - 鼓励总部经济发展\n\n'
      + '**二、科技扶持类**\n1. 深圳高新区高新技术企业培育资助 - 支持高新技术企业培育\n'
      + '2. 深圳高新区高新区加快发展新兴产业政策 - 推动新兴产业发展\n\n'
      + '**三、坪山园区专项**\n1. 深圳国家高新区坪山园区企业研发机构 - 鼓励企业建立研发机构\n'
      + '2. 深圳国家高新区坪山园区科技创新平台 - 支持科技创新平台建设\n\n建议您重点关注以上政策，具体申报条件请查阅各政策原文。',
    source: 'both',
    reasoning_paths: [],
    new_policies_count: 3,
  },
  {
    push_time: '2026-05-16 21:59:22',
    profile: { ...MOCK_PROFILE },
    query: '深圳市 科技型中小企业 人工智能 能享受什么政策补贴？',
    has_match: false,
    matched_policies: [],
    kg_rag_answer: '',
    llm_direct_answer:
      '根据您提供的企业信息（深圳市、科技型中小企业、人工智能），'
      + '目前知识库中暂时没有匹配到完全符合的新政策。建议您定期关注以下渠道获取最新政策信息：\n\n'
      + '1. 深圳市工业和信息化局官网\n'
      + '2. 深圳国家高新区管委会通知公告\n'
      + '3. 坪山区政府门户网站\n\n'
      + '我们将持续为您监控新发布政策并及时推送。',
    source: 'llm_direct',
    reasoning_paths: [],
    new_policies_count: 0,
  },
  {
    push_time: '2026-05-16 22:08:16',
    profile: { ...MOCK_PROFILE },
    query: '深圳市 科技型中小企业 人工智能 能享受什么政策补贴？',
    has_match: false,
    matched_policies: [],
    kg_rag_answer: '',
    llm_direct_answer: '当前时段未匹配到新的适用政策。',
    source: 'llm_direct',
    reasoning_paths: [],
    new_policies_count: 0,
  },
  {
    push_time: '2026-05-16 22:16:33',
    profile: { ...MOCK_PROFILE },
    query: '深圳市 科技型中小企业 人工智能 能享受什么政策补贴？',
    has_match: false,
    matched_policies: [],
    kg_rag_answer: '',
    llm_direct_answer: '当前时段未匹配到新的适用政策。',
    source: 'llm_direct',
    reasoning_paths: [],
    new_policies_count: 0,
  },
]

/** 模拟延迟 */
function delay(ms = 300): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** Mock: 获取企业画像 */
export async function mockFetchProfile(): Promise<EnterpriseProfile> {
  await delay()
  return { ...MOCK_PROFILE }
}

/** Mock: 保存企业画像 */
export async function mockSaveProfile(_profile: EnterpriseProfile): Promise<{ status: string; message: string }> {
  await delay()
  return { status: 'ok', message: '企业画像已保存（Mock）' }
}

/** Mock: 获取推送记录 */
export async function mockFetchPushRecords(date?: string): Promise<{ total: number; records: PushRecord[] }> {
  await delay(500)
  if (date) {
    const filtered = MOCK_RECORDS.filter((r) => r.push_time.startsWith(date.slice(0, 4) + '-' + date.slice(4, 6) + '-' + date.slice(6, 8)))
    return { total: filtered.length, records: filtered }
  }
  return { total: MOCK_RECORDS.length, records: [...MOCK_RECORDS] }
}
