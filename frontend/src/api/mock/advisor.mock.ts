import type { AdvisorResult } from '../types/advisor'

// Mock 决策查询结果（基于真实数据 sme_manufacturing.json）
const mockAdvisorResult: AdvisorResult = {
  query: '深圳中小企业制造业能享受什么政策',
  profile: {
    region: '深圳',
    company_type: '中小企业',
    industry: '制造业',
    intent_summary: '用户想了解深圳地区的中小企业制造业可以享受的政策',
  },
  source: 'both',
  kg_rag_answer: `根据您提供的信息（深圳中小企业、制造业），结合《深圳市有力有效支持发展瞪羚企业、独角兽企业行动计划（2025—2027年）》和《深圳市研发投入补助计划项目管理办法》，以下是个性化的政策建议：

### 1. 直接降低研发成本：利用研发费用补贴与加计扣除
- **财政补贴**：根据《深圳市研发投入补助计划项目管理办法》，对符合条件的制造业企业研发费用，可按政策给予补贴。
- **税收优惠**：对制造业企业的研发费用，可享受加计扣除。

### 2. 拓宽融资渠道：量身定制组合融资方案
- **"投贷联动"模式**：若企业属于"瞪羚企业"或"独角兽企业"培育库，可要求金融机构按需求给予"股权+债权"组合融资。
- **前海股权交易中心"专精特新"专板**：建议企业先申请"专精特新"中小企业认定。

### 3. 降低经营风险：利用风险补偿与保险创新
- **首贷/信用贷风险补偿**：制造业企业首次从银行获得贷款，可对接政策中的"风险补偿机制"。
- **支持科技创新专项担保计划**：申请纳入该计划后，政府性担保机构可提供增信。

### 4. 人才与住房支持：稳定技术团队
- **人才安居工程**：对制造业企业急需的技术骨干，可申请人才住房或租房补贴。

### 5. 市场拓展支持：展会补贴
- 参加国内外行业展会时，可根据政策申请"实际发生展位费一定比例的资助"。`,
  llm_direct_answer: `根据您的描述（深圳中小企业、制造业），结合深圳市现有政策体系，以下是为您梳理的实用政策建议：

### 一、支持方向与适用政策

1. **总部经济与龙头企业奖励**  
   - 认定为深圳市总部企业后，可享受落户奖励（最高5000万元）、贡献奖励、办公用房补贴等。

2. **工业投资与技术改造补贴**  
   - 对固定资产投资额超过500万元的技术改造项目，按设备投资额的10%-20%给予补贴，单个项目最高5000万元。

3. **智能制造与数字化升级**  
   - 获评国家级智能制造示范工厂，给予最高500万元奖励。

4. **绿色制造与节能降碳**  
   - 获评国家级绿色工厂，奖励100万元。

5. **人才与研发支持**  
   - 企业高管、核心技术人才可申请"产业发展与创新人才奖"，最高150万元。

6. **产业空间与租金补贴**  
   - 符合条件的重点产业项目可申请租用创新型产业用房，租金按市场价30%-50%优惠。`,
  reasoning_paths: [
    {
      policy: '深圳市有力有效支持发展瞪羚企业、独角兽企业行动计划（2025—2027年）',
      conditions: [
        { category: 'region', value: '深圳' },
        { category: 'company_type', value: '中小企业' },
      ],
      action_type: '融资类',
      action_raw: ['投贷联动', '专精特新专板'],
      strategies: ['扩大融资能力', '扩产'],
      sub_paths: [
        {
          subject: 'Policy(深圳市有力有效支持发展瞪羚企业、独角兽企业行动计划)',
          relation: 'has_eligibility',
          object: 'Condition(深圳)',
          source_chunk_id: 'chunk_001',
          source_text: '',
        },
        {
          subject: 'Policy(深圳市有力有效支持发展瞪羚企业、独角兽企业行动计划)',
          relation: 'provides',
          object: 'ActionType(融资类)',
          source_chunk_id: 'chunk_003',
          source_text: '',
        },
        {
          subject: 'ActionType(融资类)',
          relation: 'leads_to',
          object: 'Strategy(扩大融资能力)',
          source_chunk_id: 'rule',
          source_text: '',
        },
      ],
      perturbation_scores: [
        {
          node: { name: '深圳', type: 'Condition', source_chunk_id: '', source_text: '' },
          display: 'Condition(深圳)',
          importance: 0.466,
          reason: '重要节点: 删除Condition(深圳)后，回答从 1481 字变为 816 字，重要性 47%',
          metric_scores: {
            char_overlap_diff: 0.45,
            entity_retention_diff: 0.38,
            keyword_coverage_diff: 0.42,
            llm_semantic_score: 0.48,
            weights: { char_overlap: 0.05, entity_retention: 0.10, keyword_coverage: 0.10, llm_semantic: 0.75 },
          },
        },
        {
          node: { name: '融资类', type: 'ActionType', source_chunk_id: '', source_text: '' },
          display: 'ActionType(融资类)',
          importance: 0.374,
          reason: '重要节点: 删除ActionType(融资类)后，回答从 1481 字变为 2732 字，重要性 37%',
          metric_scores: {
            char_overlap_diff: 0.32,
            entity_retention_diff: 0.28,
            keyword_coverage_diff: 0.35,
            llm_semantic_score: 0.39,
            weights: { char_overlap: 0.05, entity_retention: 0.10, keyword_coverage: 0.10, llm_semantic: 0.75 },
          },
        },
      ],
    },
    {
      policy: '深圳市科技创新局关于印发《深圳市研发投入补助计划项目管理办法》的通知',
      conditions: [
        { category: 'region', value: '深圳' },
        { category: 'industry', value: '制造业' },
      ],
      action_type: '财政类',
      action_raw: ['研发费用补贴'],
      strategies: ['降低成本', '增加投入'],
      sub_paths: [
        {
          subject: 'Policy(深圳市研发投入补助计划项目管理办法)',
          relation: 'has_eligibility',
          object: 'Condition(深圳)',
          source_chunk_id: 'chunk_001',
          source_text: '',
        },
        {
          subject: 'Policy(深圳市研发投入补助计划项目管理办法)',
          relation: 'provides',
          object: 'ActionType(财政类)',
          source_chunk_id: 'chunk_002',
          source_text: '',
        },
        {
          subject: 'ActionType(财政类)',
          relation: 'leads_to',
          object: 'Strategy(降低成本)',
          source_chunk_id: 'rule',
          source_text: '',
        },
      ],
      perturbation_scores: [
        {
          node: {
            name: '深圳市研发投入补助计划项目管理办法',
            type: 'Policy',
            source_chunk_id: '',
            source_text: '',
          },
          display: 'Policy(深圳市研发投入补助计划项目管理办法)',
          importance: 0.31,
          reason: '重要节点: 删除此政策后，相关研发补贴建议消失',
          metric_scores: {
            char_overlap_diff: 0.25,
            entity_retention_diff: 0.22,
            keyword_coverage_diff: 0.28,
            llm_semantic_score: 0.33,
            weights: { char_overlap: 0.05, entity_retention: 0.10, keyword_coverage: 0.10, llm_semantic: 0.75 },
          },
        },
      ],
    },
  ],
  matched_policies: [
    '深圳市有力有效支持发展瞪羚企业、独角兽企业行动计划（2025—2027年）',
    '深圳市科技创新局关于印发《深圳市研发投入补助计划项目管理办法》的通知',
  ],
  matched_actions: ['人才类', '投资类', '税收类', '融资类', '财政类', '风险类'],
  matched_strategies: ['增加投入', '扩产', '扩大融资能力', '扩张业务', '提升能力', '提高利润', '降低成本', '降低融资门槛'],
  explanation: {
    summary: '重要的补充因素包括Condition(深圳)、ActionType(人才类)、Policy(深圳市科技创新局关于印发《深圳市研发投入补助计划项目管理办法》的通知)。另有 14 个次要因素。',
    key_factors: [
      { name: '深圳', type: 'Condition', importance: 0.466, description: '重要节点: 删除Condition(深圳)后，回答从 1481 字变为 816 字，重要性 47%' },
      { name: '人才类', type: 'ActionType', importance: 0.374, description: '重要节点: 删除ActionType(人才类)后，回答从 1481 字变为 2732 字，重要性 37%' },
      { name: '深圳市研发投入补助计划项目管理办法', type: 'Policy', importance: 0.31, description: '重要节点: 删除此政策后，相关研发补贴建议消失' },
    ],
    detail_text: '关键因素分析：Condition(深圳)是最重要的因素，删除后回答缩减45%；ActionType(人才类)删除后回答反而增长84%，说明它在约束回答范围方面起关键作用；Policy(研发投入补助)删除后研发相关建议消失，直接影响建议完整性。',
  },
}

// 模拟查询（带延迟）
export async function mockAdvise(query: string): Promise<AdvisorResult> {
  await new Promise(resolve => setTimeout(resolve, 1500))
  // 用 mock 数据但替换 query
  return {
    ...mockAdvisorResult,
    query,
  }
}

export default mockAdvisorResult
