<template>
  <div class="page-container">
    <div class="dashboard-header">
      <div>
        <h2>仪表盘</h2>
        <p class="subtitle">知识图谱统计概览 — FinPolicyKG 智能决策系统</p>
      </div>
      <div class="header-actions">
        <el-tag type="success" effect="plain" size="small">● 系统正常</el-tag>
        <span class="update-time">最近更新：{{ lastUpdate }}</span>
      </div>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="16" style="margin-top: 20px;">
      <el-col :span="6" v-for="stat in statCards" :key="stat.label">
        <div class="stat-card card">
          <div class="stat-top">
            <div class="stat-icon" :style="{ background: stat.iconBg, color: stat.iconColor }">{{ stat.icon }}</div>
            <div class="stat-trend" v-if="stat.trend" :class="stat.trend > 0 ? 'trend-up' : 'trend-down'">
              {{ stat.trend > 0 ? '↑' : '↓' }} {{ Math.abs(stat.trend) }}%
            </div>
          </div>
          <div class="stat-value">{{ stat.value }}</div>
          <div class="stat-label">{{ stat.label }}</div>
          <div class="stat-desc">{{ stat.desc }}</div>
        </div>
      </el-col>
    </el-row>

    <!-- 图表区域 -->
    <el-row :gutter="16" style="margin-top: 20px;">
      <el-col :span="12">
        <div class="card">
          <h3>实体类型分布</h3>
          <div ref="entityChartRef" style="height: 360px;"></div>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="card">
          <h3>关系类型分布</h3>
          <div ref="relationChartRef" style="height: 300px;"></div>
        </div>
      </el-col>
    </el-row>

    <!-- 政策列表 + 系统信息 -->
    <el-row :gutter="16" style="margin-top: 20px;">
      <el-col :span="16">
        <div class="card">
          <div class="card-header">
            <h3>已收录政策</h3>
            <el-tag size="small" type="info">{{ policies.length }} 条</el-tag>
          </div>
          <el-table :data="policies" stripe style="margin-top: 12px;" size="small">
            <el-table-column prop="name" label="政策名称" min-width="300" show-overflow-tooltip />
            <el-table-column prop="level" label="级别" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.level === '市级' ? 'primary' : row.level === '区级' ? 'warning' : 'info'" size="small">
                  {{ row.level }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="80" align="center">
              <template #default="{ row }">
                <span class="status-dot" :class="row.status"></span>
                {{ row.status === 'active' ? '有效' : '已更新' }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="card">
          <h3>🔍 系统概览</h3>
          <div class="system-info">
            <div class="info-item">
              <span class="info-label">数据来源</span>
              <span class="info-value">{{ stats.policy_document_count || 9 }} 个政策源</span>
            </div>
            <div class="info-item">
              <span class="info-label">已入库政策</span>
              <span class="info-value">{{ stats.policy_document_count || 0 }} 份文件</span>
            </div>
            <div class="info-item">
              <span class="info-label">知识图谱</span>
              <span class="info-value">{{ stats.total_entities }} 实体 / {{ stats.total_triples }} 三元组</span>
            </div>
            <div class="info-item">
              <span class="info-label">评估模型</span>
              <span class="info-value">KG-PQAM 4指标加权</span>
            </div>
            <el-divider />
            <div class="info-item">
              <span class="info-label">后端状态</span>
              <el-tag :type="backendStatus === 'online' ? 'success' : 'danger'" size="small">
                {{ backendStatus === 'online' ? '运行中' : '离线' }}
              </el-tag>
            </div>
            <div class="info-item">
              <span class="info-label">图数据库</span>
              <el-tag :type="neo4jStatus === 'online' ? 'success' : 'danger'" size="small">
                {{ neo4jStatus === 'online' ? 'Neo4j 在线' : 'Neo4j 离线' }}
              </el-tag>
            </div>
          </div>
        </div>
        <div class="card" style="margin-top: 16px;">
          <h3>🎯 快速操作</h3>
          <div class="quick-actions">
            <router-link to="/advisor" class="action-link">
              <el-button type="primary" style="width: 100%;">🔍 政策决策查询</el-button>
            </router-link>
            <router-link to="/kg-explorer" class="action-link">
              <el-button style="width: 100%; margin-top: 8px;">🕸️ 浏览知识图谱</el-button>
            </router-link>
          </div>
        </div>

        <!-- 最新推送卡片 -->
        <div v-if="latestPush" class="card latest-push-card" style="margin-top: 16px;">
          <div class="card-header-row">
            <h3>📬 最新推送</h3>
            <router-link to="/push-records" class="view-all">查看全部 →</router-link>
          </div>
          <div class="push-summary">
            <div class="push-time">{{ latestPush.push_time }}</div>
            <div class="push-status">
              <el-tag v-if="latestPush.has_match" type="success" size="small" effect="dark">
                ✅ 匹配 {{ latestPush.matched_policies.length }} 条政策
              </el-tag>
              <el-tag v-else type="info" size="small" effect="plain">❌ 无新匹配</el-tag>
              <el-tag v-if="latestPush.new_policies_count > 0" size="small" type="warning" style="margin-left: 4px;">
                🆕 {{ latestPush.new_policies_count }} 份新政
              </el-tag>
            </div>
            <div v-if="latestPush.matched_policies.length > 0" class="push-policies">
              <div v-for="(p, i) in latestPush.matched_policies.slice(0, 3)" :key="i" class="push-policy-item">
                {{ p }}
              </div>
              <div v-if="latestPush.matched_policies.length > 3" class="push-more">
                +{{ latestPush.matched_policies.length - 3 }} 条更多
              </div>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import * as echarts from 'echarts'
import { fetchKGStats } from '../api/kg'
import { fetchPushRecords } from '../api/push'
import { getNodeColor, getRelColor } from '../utils/color'

const entityChartRef = ref<HTMLElement>()
const relationChartRef = ref<HTMLElement>()

const lastUpdate = '2026-05-10'
const sources = ['国家发改委', '广东省政府', '深圳市政府', '坪山区', '宝安区', '南山区']

// 后端状态
const backendStatus = ref<'online' | 'offline'>('online')
const neo4jStatus = ref<'online' | 'offline'>('online')

// 最新推送
const latestPush = ref<any>(null)

// 实体类型中文映射
function getEntityLabel(type: string): string {
  const labels: Record<string, string> = {
    Policy: '政策',
    Condition: '条件',
    ActionType: '措施',
    Strategy: '策略',
    Institution: '机构',
    FinancialConcept: '金融概念',
    Indicator: '指标',
    Event: '事件',
    Industry: '行业',
    CompanyType: '企业类型',
    Document: '文档',
    Market: '市场',
    Region: '地区',
    Person: '人物',
  }
  return labels[type] || type
}

// 关系类型中文映射
function getRelationLabel(type: string): string {
  const labels: Record<string, string> = {
    has_eligibility: '适用条件',
    sets: '设定',
    provides: '提供',
    targets: '针对',
    has_indicator: '有指标',
    leads_to: '导向',
    references: '引用',
    mentions: '提及',
    cites_as_basis: '引用依据',
    affects: '影响',
    issues: '发布',
    subregion_of: '子区域',
    repeals: '废止',
  }
  return labels[type] || type
}

const stats = ref({
  total_entities: 0,
  total_triples: 0,
  entity_type_distribution: {} as Record<string, number>,
  relation_type_distribution: {} as Record<string, number>,
  policy_document_count: 0,
  policy_documents: [] as string[],
})

const statCards = ref([
  { label: '实体总数', value: 0, icon: '🕸️', iconBg: '#f0f0f0', iconColor: '#999', desc: '知识图谱节点数', trend: 12 },
  { label: '三元组总数', value: 0, icon: '🔗', iconBg: '#f0f0f0', iconColor: '#999', desc: '知识图谱边数', trend: 8 },
  { label: '政策文档', value: 0, icon: '📋', iconBg: '#f0f0f0', iconColor: '#999', desc: '已入库政策文件', trend: 0 },
  { label: '措施类型', value: 0, icon: '🎯', iconBg: '#f0f0f0', iconColor: '#999', desc: '6 大类措施分类', trend: 0 },
])

const policies = ref<Array<{ name: string; level: string; status: string }>>([])

onMounted(async () => {
  const data = await fetchKGStats()
  stats.value = data

  // 健康检查
  try {
    const { default: client } = await import('../api/client')
    const health: any = await client.get('/health')
    backendStatus.value = 'online'
    neo4jStatus.value = health.neo4j ? 'online' : 'offline'
  } catch {
    backendStatus.value = 'offline'
    neo4jStatus.value = 'offline'
  }

  // 加载最新推送记录
  try {
    const pushResult = await fetchPushRecords()
    if (pushResult.records.length > 0) {
      latestPush.value = pushResult.records[0]
    }
  } catch {
    // 推送记录加载失败不影响主流程
  }

  statCards.value = [
    { label: '实体总数', value: data.total_entities, icon: '🕸️', iconBg: '#f0f0f0', iconColor: '#999', desc: '知识图谱节点数', trend: 12 },
    { label: '三元组总数', value: data.total_triples, icon: '🔗', iconBg: '#f0f0f0', iconColor: '#999', desc: '知识图谱边数', trend: 8 },
    { label: '政策文档', value: data.policy_document_count || 0, icon: '📋', iconBg: '#f0f0f0', iconColor: '#999', desc: '已入库政策文件', trend: 0 },
    { label: '措施类型', value: data.entity_type_distribution.ActionType || 0, icon: '🎯', iconBg: '#f0f0f0', iconColor: '#999', desc: '6 大类措施分类', trend: 0 },
  ]

  // 政策列表：从后端返回的 policy_documents 生成
  policies.value = (data.policy_documents || []).slice(0, 50).map((name: string) => {
    // 去除 _ 和 - 让文件名更可读
    const displayName = name
      .replace(/\.pdf$/i, '')
      .replace(/_/g, ' ')
      .replace(/-/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
    return {
      name: displayName,
      level: name.includes('坪山') || name.includes('宝安') ? '区级' : '市级',
      status: 'active',
    }
  })

  // 如果后端没有 policy_documents，fallback 到 Policy 节点去重（兼容旧数据）
  if (policies.value.length === 0 && data.entity_type_distribution.Policy) {
    // 从节点名中尝试提取文档级政策
    try {
      const { fetchGraphData } = await import('../api/kg')
      const graph = await fetchGraphData()
      const docNames = new Set<string>()
      for (const node of graph.nodes || []) {
        if (node.type === 'Policy' && node.name.length > 8) {
          // 去掉短名（条款级）和常见非政策名
          if (!node.name.includes('第') && !['政策', '专项资金'].includes(node.name)) {
            docNames.add(node.name)
          }
        }
      }
      policies.value = Array.from(docNames).slice(0, 50).map(name => ({
        name,
        level: name.includes('坪山') || name.includes('宝安') ? '区级' : '市级',
        status: 'active',
      }))
    } catch {
      // ignore
    }
  }

  // 实体类型分布饼图
  if (entityChartRef.value) {
    const chart = echarts.init(entityChartRef.value)
    chart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { bottom: 0, textStyle: { fontSize: 11 }, itemWidth: 10, itemHeight: 10 },
      series: [{
        type: 'pie',
        radius: ['30%', '55%'],
        center: ['50%', '42%'],
        avoidLabelOverlap: true,
        padAngle: 1,
        data: Object.entries(data.entity_type_distribution).map(([name, value]) => ({
          name: getEntityLabel(name),
          value,
          itemStyle: { color: getNodeColor(name) },
        })),
        label: {
          show: true,
          formatter: '{b}',
          fontSize: 11,
          position: 'outside',
        },
        labelLine: { length: 6, length2: 8 },
        emphasis: {
          itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,0.15)' },
          label: { show: true, fontSize: 13, fontWeight: 500, formatter: '{b}\n{d}%' },
        },
      }],
    })
    window.addEventListener('resize', () => chart.resize())
  }

  // 关系类型分布柱状图
  if (relationChartRef.value) {
    const chart = echarts.init(relationChartRef.value)
    const entries = Object.entries(data.relation_type_distribution)
    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { top: 20, bottom: 60, left: 50, right: 20 },
      xAxis: {
        type: 'category',
        data: entries.map(([k]) => getRelationLabel(k)),
        axisLabel: { rotate: 30, fontSize: 11 },
      },
      yAxis: { type: 'value', axisLabel: { fontSize: 11 } },
      series: [{
        type: 'bar',
        data: entries.map(([k, v]) => ({
          value: v,
          itemStyle: { color: getRelColor(k) },
        })),
        barWidth: 32,
        label: { show: true, position: 'top', fontSize: 12, fontWeight: 600 },
      }],
    })
    window.addEventListener('resize', () => chart.resize())
  }
})
</script>

<style scoped lang="scss">
h2 { color: var(--color-text); font-size: 22px; margin: 0; }
h3 { font-size: 16px; color: var(--color-text); margin-bottom: 4px; }

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;

  .subtitle {
    color: var(--color-text-secondary);
    margin-top: 4px;
    font-size: 14px;
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 12px;
    .update-time { font-size: 12px; color: var(--color-text-placeholder); }
  }
}

.stat-card {
  padding: 20px 16px;

  .stat-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }

  .stat-icon {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
  }

  .stat-trend {
    font-size: 12px;
    font-weight: 600;
    &.trend-up { color: #10b981; }
    &.trend-down { color: #ef4444; }
  }

  .stat-value {
    font-size: 32px;
    font-weight: 700;
    color: var(--color-text);
    line-height: 1.2;
  }

  .stat-label {
    font-size: 14px;
    color: var(--color-text);
    margin-top: 4px;
    font-weight: 500;
  }

  .stat-desc {
    font-size: 12px;
    color: var(--color-text-secondary);
    margin-top: 2px;
  }
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.status-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 4px;
  &.active { background: #10b981; }
  &.updated { background: #f59e0b; }
}

.system-info {
  margin-top: 8px;
  .info-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid var(--color-border-light);
    .info-label { font-size: 13px; color: var(--color-text-secondary); }
    .info-value { font-size: 13px; font-weight: 500; color: var(--color-text); }
  }
}

.quick-actions {
  margin-top: 12px;
  .action-link {
    text-decoration: none;
  }
}

/* 最新推送卡片 */
.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  h3 { margin-bottom: 0; }
  .view-all { font-size: 12px; color: #3b82f6; text-decoration: none; }
}
.latest-push-card {
  .push-time { font-size: 13px; color: var(--color-text-secondary); margin-bottom: 8px; }
  .push-policies { margin-top: 8px; }
  .push-policy-item {
    font-size: 13px; color: var(--color-text-primary); padding: 2px 0;
    &::before { content: '• '; color: var(--color-primary); }
  }
  .push-more { font-size: 12px; color: var(--color-text-secondary); margin-top: 2px; }
}
</style>
