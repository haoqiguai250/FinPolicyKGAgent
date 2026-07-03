// KG 节点类型颜色映射 — 覆盖全部 14 种实体类型
export const nodeTypeColors: Record<string, string> = {
  Policy: '#3b82f6',           // 蓝 — 政策
  Condition: '#f59e0b',        // 琥珀 — 适用条件
  ActionType: '#f97316',       // 橙 — 措施类型
  Strategy: '#10b981',        // 翠绿 — 策略
  Institution: '#6366f1',     // 靛蓝 — 机构
  FinancialConcept: '#8b5cf6',// 紫 — 金融概念
  Indicator: '#06b6d4',       // 青 — 指标
  Event: '#ec4899',           // 粉 — 事件
  Industry: '#14b8a6',        // 深青 — 行业
  CompanyType: '#a855f7',     // 浅紫 — 企业类型
  Document: '#64748b',        // 石板 — 文档
  Market: '#0ea5e9',          // 天蓝 — 市场
  Region: '#f43f5e',          // 玫红 — 地区
  Person: '#d946ef',          // 紫红 — 人物
}

// KG 关系类型颜色映射 — 覆盖全部 13 种关系类型
export const relationTypeColors: Record<string, string> = {
  has_eligibility: '#f59e0b',  // 琥珀
  sets: '#6366f1',            // 靛蓝
  provides: '#3b82f6',        // 蓝
  targets: '#8b5cf6',         // 紫
  has_indicator: '#06b6d4',   // 青
  leads_to: '#10b981',        // 翠绿
  references: '#94a3b8',      // 浅石板
  mentions: '#a855f7',        // 浅紫
  cites_as_basis: '#0ea5e9',  // 天蓝
  affects: '#f97316',         // 橙
  issues: '#14b8a6',          // 深青
  subregion_of: '#f43f5e',    // 玫红
  repeals: '#ef4444',         // 红
}

// 扰动分析等级
export const perturbationLevel = {
  critical: { color: '#ef4444', label: '关键', threshold: 0.7 },
  important: { color: '#f59e0b', label: '重要', threshold: 0.3 },
  minor: { color: '#9ca3af', label: '次要', threshold: 0 },
}

// 根据 importance 值返回等级
export function getPerturbationLevel(importance: number) {
  if (importance > perturbationLevel.critical.threshold) {
    return perturbationLevel.critical
  } else if (importance > perturbationLevel.important.threshold) {
    return perturbationLevel.important
  }
  return perturbationLevel.minor
}

// 获取节点颜色
export function getNodeColor(type: string): string {
  return nodeTypeColors[type] || '#6b7280'
}

// 获取关系颜色
export function getRelColor(type: string): string {
  return relationTypeColors[type] || '#6b7280'
}
