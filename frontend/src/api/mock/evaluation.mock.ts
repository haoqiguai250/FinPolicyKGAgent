import type { EvaluationData } from '../types/evaluation'

export const mockEvaluationData: EvaluationData = {
  summary: {
    total_docs: 6,
    avg_l1: 86.2,
    avg_l2: 71.8,
    avg_l3: 66.5,
    avg_l4: 76.8,
  },
  reports: [
    {
      id: 'rpt-20260509-001',
      doc_name: '深圳市有力有效支持发展瞪羚企业、独角兽企业行动计划（2025—2027年）',
      timestamp: '2026-05-09 14:30:00',
      l1: {
        overall_rate: 85.7,
        rules: [
          { rule: 'R1: 实体名非空', description: '所有三元组的主体和客体实体名称不能为空', pass: true, rate: 100, details: '共 48 个实体，全部非空' },
          { rule: 'R2: 实体名长度合规', description: '实体名长度应 ≤ 50 字符', pass: false, rate: 71.4, details: '15/21 个 Policy 实体名超过 50 字符，建议截断或缩写' },
          { rule: 'R3: 关系名在 Schema 内', description: '关系类型必须属于预定义 Schema', pass: true, rate: 100, details: '所有 67 条关系均在 Schema 内' },
          { rule: 'R4: 三元组主语/宾语存在', description: '三元组引用的实体必须存在于实体库中', pass: true, rate: 100, details: '所有三元组的实体引用均有效' },
        ],
      },
      l2: {
        ecr: 0.78,
        tcr: 0.72,
        rcr: 0.67,
        doc_breakdown: [
          { doc_name: '瞪羚企业行动计划', ecr: 0.82, tcr: 0.75, rcr: 0.71 },
          { doc_name: '研发投入补助管理办法', ecr: 0.76, tcr: 0.70, rcr: 0.65 },
          { doc_name: '坪山区支持实体经济措施', ecr: 0.74, tcr: 0.68, rcr: 0.62 },
          { doc_name: '人工智能+先进制造业', ecr: 0.80, tcr: 0.74, rcr: 0.70 },
          { doc_name: '宝安监管局三大计划', ecr: 0.68, tcr: 0.63, rcr: 0.58 },
        ],
      },
      l3: {
        shannon_entropy: 3.42,
        renyi_entropy: 2.87,
        type_distribution: {
          Policy: 0.18,
          Condition: 0.32,
          ActionType: 0.12,
          Strategy: 0.15,
          Company: 0.08,
          Region: 0.15,
        },
        diversity_score: 68,
      },
      l4: {
        dimensions: [
          { name: '精确性', score: 82, color: '#3b82f6' },
          { name: '忠实度', score: 76, color: '#10b981' },
          { name: '完整性', score: 74, color: '#f59e0b' },
          { name: '相关性', score: 82, color: '#8b5cf6' },
        ],
        overall_score: 78.5,
        llm_judge_comments: '整体抽取质量良好。Policy 实体识别精确，但部分 Condition 实体粒度过细导致信息冗余；关系抽取忠实度高，但在"references"关系上存在约 15 条被过度约束过滤的情况。建议：(1) 放宽 R2 实体长度限制至 80 字符；(2) 优化 Condition 实体的归一化策略；(3) 调整 references 关系的约束条件。',
        doc_scores: [
          { doc_name: '瞪羚企业行动计划', precision: 85, faithfulness: 80, completeness: 78, relevance: 84 },
          { doc_name: '研发投入补助管理办法', precision: 82, faithfulness: 78, completeness: 72, relevance: 80 },
          { doc_name: '坪山区支持实体经济措施', precision: 78, faithfulness: 74, completeness: 70, relevance: 76 },
          { doc_name: '人工智能+先进制造业', precision: 84, faithfulness: 76, completeness: 75, relevance: 82 },
          { doc_name: '宝安监管局三大计划', precision: 72, faithfulness: 68, completeness: 65, relevance: 70 },
        ],
      },
    },
    {
      id: 'rpt-20260509-002',
      doc_name: '深圳市研发投入补助计划项目管理办法',
      timestamp: '2026-05-09 14:28:00',
      l1: {
        overall_rate: 90.2,
        rules: [
          { rule: 'R1: 实体名非空', description: '所有三元组的主体和客体实体名称不能为空', pass: true, rate: 100, details: '共 36 个实体，全部非空' },
          { rule: 'R2: 实体名长度合规', description: '实体名长度应 ≤ 50 字符', pass: false, rate: 80.0, details: '4/20 个 Policy 实体名超过 50 字符' },
          { rule: 'R3: 关系名在 Schema 内', description: '关系类型必须属于预定义 Schema', pass: true, rate: 100, details: '所有 42 条关系均在 Schema 内' },
          { rule: 'R4: 三元组主语/宾语存在', description: '三元组引用的实体必须存在于实体库中', pass: true, rate: 100, details: '所有三元组的实体引用均有效' },
        ],
      },
      l2: { ecr: 0.76, tcr: 0.70, rcr: 0.65, doc_breakdown: [] },
      l3: {
        shannon_entropy: 3.18,
        renyi_entropy: 2.64,
        type_distribution: { Policy: 0.22, Condition: 0.28, ActionType: 0.14, Strategy: 0.18, Company: 0.06, Region: 0.12 },
        diversity_score: 64,
      },
      l4: {
        dimensions: [
          { name: '精确性', score: 80, color: '#3b82f6' },
          { name: '忠实度', score: 74, color: '#10b981' },
          { name: '完整性', score: 70, color: '#f59e0b' },
          { name: '相关性', score: 78, color: '#8b5cf6' },
        ],
        overall_score: 75.5,
        llm_judge_comments: '抽取质量中等偏上。研发补助类条件识别较准，但"适用条件"归一化不够，存在同义不同名的情况。',
        doc_scores: [],
      },
    },
    {
      id: 'rpt-20260508-001',
      doc_name: '深圳市坪山区关于支持实体经济高质量发展的若干措施',
      timestamp: '2026-05-08 16:45:00',
      l1: {
        overall_rate: 88.0,
        rules: [
          { rule: 'R1: 实体名非空', description: '所有三元组的主体和客体实体名称不能为空', pass: true, rate: 100, details: '共 42 个实体，全部非空' },
          { rule: 'R2: 实体名长度合规', description: '实体名长度应 ≤ 50 字符', pass: false, rate: 76.2, details: '5/21 个 Policy 实体名超过 50 字符' },
          { rule: 'R3: 关系名在 Schema 内', description: '关系类型必须属于预定义 Schema', pass: true, rate: 100, details: '所有 55 条关系均在 Schema 内' },
          { rule: 'R4: 三元组主语/宾语存在', description: '三元组引用的实体必须存在于实体库中', pass: true, rate: 100, details: '所有三元组的实体引用均有效' },
        ],
      },
      l2: {
        ecr: 0.72,
        tcr: 0.66,
        rcr: 0.61,
        doc_breakdown: [
          { doc_name: '坪山区实体经济措施', ecr: 0.72, tcr: 0.66, rcr: 0.61 },
          { doc_name: '坪山区科技创新扶持', ecr: 0.70, tcr: 0.64, rcr: 0.58 },
        ],
      },
      l3: {
        shannon_entropy: 3.05,
        renyi_entropy: 2.52,
        type_distribution: { Policy: 0.20, Condition: 0.30, ActionType: 0.10, Strategy: 0.18, Company: 0.10, Region: 0.12 },
        diversity_score: 61,
      },
      l4: {
        dimensions: [
          { name: '精确性', score: 76, color: '#3b82f6' },
          { name: '忠实度', score: 72, color: '#10b981' },
          { name: '完整性', score: 68, color: '#f59e0b' },
          { name: '相关性', score: 74, color: '#8b5cf6' },
        ],
        overall_score: 72.5,
        llm_judge_comments: '区级政策抽取质量中等。措施条款识别较好，但"适用对象"与"适用条件"的区分不够清晰，部分实体边界模糊。建议优化 Condition 和 targets 的区分规则。',
        doc_scores: [
          { doc_name: '坪山区实体经济措施', precision: 76, faithfulness: 72, completeness: 68, relevance: 74 },
          { doc_name: '坪山区科技创新扶持', precision: 74, faithfulness: 70, completeness: 66, relevance: 72 },
        ],
      },
    },
    {
      id: 'rpt-20260508-002',
      doc_name: '深圳市人工智能+先进制造业发展行动计划',
      timestamp: '2026-05-08 11:20:00',
      l1: {
        overall_rate: 92.5,
        rules: [
          { rule: 'R1: 实体名非空', description: '所有三元组的主体和客体实体名称不能为空', pass: true, rate: 100, details: '共 56 个实体，全部非空' },
          { rule: 'R2: 实体名长度合规', description: '实体名长度应 ≤ 50 字符', pass: true, rate: 95.0, details: '1/20 个 Policy 实体名超过 50 字符' },
          { rule: 'R3: 关系名在 Schema 内', description: '关系类型必须属于预定义 Schema', pass: true, rate: 100, details: '所有 72 条关系均在 Schema 内' },
          { rule: 'R4: 三元组主语/宾语存在', description: '三元组引用的实体必须存在于实体库中', pass: true, rate: 100, details: '所有三元组的实体引用均有效' },
        ],
      },
      l2: {
        ecr: 0.82,
        tcr: 0.76,
        rcr: 0.72,
        doc_breakdown: [
          { doc_name: '人工智能+制造业', ecr: 0.82, tcr: 0.76, rcr: 0.72 },
          { doc_name: '智能制造专项', ecr: 0.80, tcr: 0.74, rcr: 0.70 },
          { doc_name: '数字化转型支持', ecr: 0.78, tcr: 0.72, rcr: 0.68 },
        ],
      },
      l3: {
        shannon_entropy: 3.56,
        renyi_entropy: 3.01,
        type_distribution: { Policy: 0.16, Condition: 0.28, ActionType: 0.14, Strategy: 0.20, Company: 0.10, Region: 0.12 },
        diversity_score: 72,
      },
      l4: {
        dimensions: [
          { name: '精确性', score: 88, color: '#3b82f6' },
          { name: '忠实度', score: 82, color: '#10b981' },
          { name: '完整性', score: 80, color: '#f59e0b' },
          { name: '相关性', score: 86, color: '#8b5cf6' },
        ],
        overall_score: 84.0,
        llm_judge_comments: '抽取质量优秀。AI 和制造业交叉领域的实体识别准确，措施与策略的映射关系清晰。Condition 标准化做得好，建议作为标杆模板。',
        doc_scores: [
          { doc_name: '人工智能+制造业', precision: 88, faithfulness: 82, completeness: 80, relevance: 86 },
          { doc_name: '智能制造专项', precision: 86, faithfulness: 80, completeness: 78, relevance: 84 },
          { doc_name: '数字化转型支持', precision: 84, faithfulness: 78, completeness: 76, relevance: 82 },
        ],
      },
    },
    {
      id: 'rpt-20260507-001',
      doc_name: '深圳市宝安区市场监管局推动三大计划实施方案',
      timestamp: '2026-05-07 09:15:00',
      l1: {
        overall_rate: 82.3,
        rules: [
          { rule: 'R1: 实体名非空', description: '所有三元组的主体和客体实体名称不能为空', pass: true, rate: 100, details: '共 30 个实体，全部非空' },
          { rule: 'R2: 实体名长度合规', description: '实体名长度应 ≤ 50 字符', pass: false, rate: 65.0, details: '7/20 个 Policy 实体名超过 50 字符' },
          { rule: 'R3: 关系名在 Schema 内', description: '关系类型必须属于预定义 Schema', pass: true, rate: 100, details: '所有 38 条关系均在 Schema 内' },
          { rule: 'R4: 三元组主语/宾语存在', description: '三元组引用的实体必须存在于实体库中', pass: true, rate: 100, details: '所有三元组的实体引用均有效' },
        ],
      },
      l2: { ecr: 0.64, tcr: 0.58, rcr: 0.52, doc_breakdown: [] },
      l3: {
        shannon_entropy: 2.78,
        renyi_entropy: 2.21,
        type_distribution: { Policy: 0.25, Condition: 0.22, ActionType: 0.18, Strategy: 0.12, Company: 0.08, Region: 0.15 },
        diversity_score: 55,
      },
      l4: {
        dimensions: [
          { name: '精确性', score: 68, color: '#3b82f6' },
          { name: '忠实度', score: 64, color: '#10b981' },
          { name: '完整性', score: 58, color: '#f59e0b' },
          { name: '相关性', score: 66, color: '#8b5cf6' },
        ],
        overall_score: 64.0,
        llm_judge_comments: '抽取质量偏低。实施方案文本结构松散，条款编号不规范，导致分割粒度不均。建议先优化 Docling 解析阶段的条款识别，再重新抽取。',
        doc_scores: [],
      },
    },
    {
      id: 'rpt-20260507-002',
      doc_name: '深圳市南山区促进低空经济发展若干措施',
      timestamp: '2026-05-07 08:50:00',
      l1: {
        overall_rate: 91.0,
        rules: [
          { rule: 'R1: 实体名非空', description: '所有三元组的主体和客体实体名称不能为空', pass: true, rate: 100, details: '共 38 个实体，全部非空' },
          { rule: 'R2: 实体名长度合规', description: '实体名长度应 ≤ 50 字符', pass: true, rate: 90.0, details: '2/20 个 Policy 实体名超过 50 字符' },
          { rule: 'R3: 关系名在 Schema 内', description: '关系类型必须属于预定义 Schema', pass: true, rate: 100, details: '所有 48 条关系均在 Schema 内' },
          { rule: 'R4: 三元组主语/宾语存在', description: '三元组引用的实体必须存在于实体库中', pass: true, rate: 100, details: '所有三元组的实体引用均有效' },
        ],
      },
      l2: {
        ecr: 0.80,
        tcr: 0.74,
        rcr: 0.68,
        doc_breakdown: [
          { doc_name: '南山区低空经济措施', ecr: 0.80, tcr: 0.74, rcr: 0.68 },
          { doc_name: '低空飞行器管理', ecr: 0.78, tcr: 0.72, rcr: 0.66 },
        ],
      },
      l3: {
        shannon_entropy: 3.35,
        renyi_entropy: 2.78,
        type_distribution: { Policy: 0.18, Condition: 0.26, ActionType: 0.16, Strategy: 0.18, Company: 0.12, Region: 0.10 },
        diversity_score: 67,
      },
      l4: {
        dimensions: [
          { name: '精确性', score: 84, color: '#3b82f6' },
          { name: '忠实度', score: 80, color: '#10b981' },
          { name: '完整性', score: 76, color: '#f59e0b' },
          { name: '相关性', score: 82, color: '#8b5cf6' },
        ],
        overall_score: 80.5,
        llm_judge_comments: '抽取质量良好。低空经济领域实体识别准确，措施分类清晰，Condition 归一化较好。人才类 Action 较少，可能是政策原文本身侧重资金和准入方面。',
        doc_scores: [
          { doc_name: '南山区低空经济措施', precision: 84, faithfulness: 80, completeness: 76, relevance: 82 },
          { doc_name: '低空飞行器管理', precision: 82, faithfulness: 78, completeness: 74, relevance: 80 },
        ],
      },
    },
  ],
}

// 模拟加载
export async function mockLoadEvaluation(): Promise<EvaluationData> {
  await new Promise(resolve => setTimeout(resolve, 800))
  return mockEvaluationData
}
