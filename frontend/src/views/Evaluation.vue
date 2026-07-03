<template>
  <div class="page-container">
    <h2>评估报告</h2>
    <p style="color: var(--color-text-secondary); margin-top: 8px;">知识图谱四层一体化评估结果 — KG-PQAM 量化评估模型</p>

    <!-- 加载态 -->
    <div v-if="loading" style="text-align: center; padding: 80px 0;">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <p style="margin-top: 12px; color: var(--color-text-secondary);">加载评估数据中...</p>
    </div>

    <template v-else-if="evalData">
      <!-- 4 个评分卡片（汇总） -->
      <el-row :gutter="16" style="margin-top: 24px;">
        <el-col :span="6" v-for="card in summaryCards" :key="card.label">
          <div class="eval-card card" :style="{ borderTopColor: card.color }">
            <div class="eval-icon" :style="{ background: card.color + '15', color: card.color }">{{ card.icon }}</div>
            <div class="eval-info">
              <div class="eval-score" :style="{ color: card.color }">{{ card.value }}</div>
              <div class="eval-label">{{ card.label }}</div>
              <div class="eval-desc">{{ card.desc }}</div>
            </div>
            <el-progress :percentage="card.percent" :color="card.color" :show-text="false" :stroke-width="4" style="margin-top: 8px;" />
          </div>
        </el-col>
      </el-row>

      <!-- Master-Detail: 左侧报告列表 + 右侧详情 -->
      <div class="report-layout" style="margin-top: 20px;">
        <!-- 左侧：报告列表 -->
        <div class="report-list-panel card">
          <div class="list-header">
            <span class="list-title">评估记录</span>
            <el-tag size="small" type="info">{{ evalData.reports.length }} 份</el-tag>
          </div>
          <el-input
            v-model="searchKeyword"
            placeholder="搜索政策名称..."
            prefix-icon="Search"
            clearable
            size="small"
            style="margin: 10px 0;"
          />
          <div class="report-list">
            <div
              v-for="(r, idx) in filteredReports"
              :key="r.id"
              class="report-item"
              :class="{ active: selectedReportId === r.id }"
              @click="selectedReportId = r.id"
            >
              <div class="item-header">
                <span class="item-name" :title="r.doc_name">{{ truncate(r.doc_name, 24) }}</span>
                <span class="item-score" :class="scoreLevel(r.l4.overall_score)">{{ r.l4.overall_score }}</span>
              </div>
              <div class="item-meta">
                <span class="item-time">{{ r.timestamp }}</span>
              </div>
              <div class="item-badges">
                <el-tag size="small" :type="r.l1.overall_rate >= 90 ? 'success' : r.l1.overall_rate >= 70 ? 'warning' : 'danger'">
                  L1 {{ r.l1.overall_rate }}%
                </el-tag>
                <el-tag size="small" type="info">
                  L3 {{ r.l3.diversity_score }}
                </el-tag>
              </div>
            </div>
            <div v-if="filteredReports.length === 0" class="empty-hint">
              无匹配的报告
            </div>
          </div>
        </div>

        <!-- 右侧：报告详情 -->
        <div class="report-detail-panel" v-if="currentReport">
          <!-- 详情头部 -->
          <div class="detail-header card">
            <div class="detail-title-row">
              <h3>{{ currentReport.doc_name }}</h3>
              <el-tag type="info" size="small">{{ currentReport.timestamp }}</el-tag>
            </div>
            <div class="detail-badges">
              <el-tag :type="currentReport.l1.overall_rate >= 90 ? 'success' : 'warning'" effect="dark" size="small">
                L1 {{ currentReport.l1.overall_rate }}%
              </el-tag>
              <el-tag color="#8b5cf6" effect="dark" size="small" style="color: #fff; border-color: #8b5cf6;">
                L4 {{ currentReport.l4.overall_score }} 分
              </el-tag>
            </div>
          </div>

          <!-- 综合雷达图 + L4 详情 -->
          <el-row :gutter="16" style="margin-top: 16px;">
            <el-col :span="10">
              <div class="card">
                <h3>🎯 四维综合评分</h3>
                <div ref="radarChartRef" style="height: 320px; margin-top: 12px;"></div>
              </div>
            </el-col>
            <el-col :span="14">
              <div class="card">
                <h3>🏆 L4 LLM 裁判评分</h3>
                <div style="margin-top: 12px;">
                  <div v-for="dim in currentReport.l4.dimensions" :key="dim.name" class="l4-dim">
                    <span class="l4-label">{{ dim.name }}</span>
                    <el-progress :percentage="dim.score" :color="dim.color" :stroke-width="14" style="flex: 1;" />
                    <span class="l4-score">{{ dim.score }}</span>
                  </div>
                </div>
                <div class="l4-comment" v-if="currentReport.l4.llm_judge_comments">
                  <div class="comment-header">💡 LLM 裁判评语</div>
                  <p class="comment-text">{{ currentReport.l4.llm_judge_comments }}</p>
                </div>
              </div>
            </el-col>
          </el-row>

          <!-- L1 规则合规 + L2 抽取效率 -->
          <el-row :gutter="16" style="margin-top: 16px;">
            <el-col :span="12">
              <div class="card">
                <h3>📋 L1 规则合规详情</h3>
                <div class="l1-overview">
                  <span>合规率：<strong>{{ currentReport.l1.overall_rate }}%</strong></span>
                  <el-tag :type="currentReport.l1.overall_rate >= 90 ? 'success' : currentReport.l1.overall_rate >= 70 ? 'warning' : 'danger'" size="small">
                    {{ currentReport.l1.overall_rate >= 90 ? '优秀' : currentReport.l1.overall_rate >= 70 ? '良好' : '待改进' }}
                  </el-tag>
                </div>
                <el-table :data="currentReport.l1.rules" stripe style="margin-top: 12px;" size="small">
                  <el-table-column prop="rule" label="规则" min-width="160" />
                  <el-table-column prop="rate" label="合规率" width="90" align="center">
                    <template #default="{ row }">
                      <span :style="{ color: row.rate === 100 ? '#10b981' : '#f59e0b', fontWeight: 600 }">{{ row.rate }}%</span>
                    </template>
                  </el-table-column>
                  <el-table-column prop="pass" label="状态" width="70" align="center">
                    <template #default="{ row }">
                      <el-tag :type="row.pass ? 'success' : 'danger'" size="small">{{ row.pass ? '通过' : '违规' }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="details" label="详情" min-width="200" show-overflow-tooltip />
                </el-table>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="card">
                <h3>📊 L2 抽取效率</h3>
                <div class="l2-metrics">
                  <div class="l2-metric-item" v-for="m in l2Summary" :key="m.label">
                    <span class="l2-metric-value" :style="{ color: m.color }">{{ m.value }}</span>
                    <span class="l2-metric-label">{{ m.label }}</span>
                  </div>
                </div>
                <div ref="barChartRef" style="height: 240px; margin-top: 8px;"></div>
              </div>
            </el-col>
          </el-row>

          <!-- L3 语义多样性 -->
          <div class="card" style="margin-top: 16px;">
            <h3>🧬 L3 语义多样性</h3>
            <el-row :gutter="24" style="margin-top: 12px;">
              <el-col :span="8">
                <div class="l3-entropy">
                  <div class="entropy-item">
                    <span class="entropy-label">Shannon 熵</span>
                    <span class="entropy-value">{{ currentReport.l3.shannon_entropy }}</span>
                  </div>
                  <div class="entropy-item">
                    <span class="entropy-label">Rényi 熵</span>
                    <span class="entropy-value">{{ currentReport.l3.renyi_entropy }}</span>
                  </div>
                  <div class="entropy-item">
                    <span class="entropy-label">多样性评分</span>
                    <span class="entropy-value" :style="{ color: currentReport.l3.diversity_score >= 70 ? '#10b981' : '#f59e0b' }">
                      {{ currentReport.l3.diversity_score }}
                    </span>
                  </div>
                  <div class="entropy-note">熵值越高，实体类型分布越均匀，知识图谱覆盖面越广</div>
                </div>
              </el-col>
              <el-col :span="16">
                <div ref="pieChartRef" style="height: 260px;"></div>
              </el-col>
            </el-row>
          </div>
        </div>

        <!-- 未选中报告时的占位 -->
        <div class="report-detail-panel empty-detail" v-else>
          <div class="empty-placeholder">
            <span style="font-size: 48px;">📋</span>
            <p>请从左侧选择一份评估报告查看详情</p>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { fetchEvaluationData } from '../api/evaluation'
import type { EvaluationData, EvaluationReport } from '../types/evaluation'
import { getNodeColor } from '../utils/color'

const loading = ref(true)
const evalData = ref<EvaluationData | null>(null)
const selectedReportId = ref<string>('')
const searchKeyword = ref('')

const radarChartRef = ref<HTMLElement>()
const barChartRef = ref<HTMLElement>()
const pieChartRef = ref<HTMLElement>()

let radarChart: echarts.ECharts | null = null
let barChart: echarts.ECharts | null = null
let pieChart: echarts.ECharts | null = null

// 当前选中的报告
const currentReport = computed(() => {
  if (!evalData.value) return null
  return evalData.value.reports.find(r => r.id === selectedReportId.value) || null
})

// 搜索过滤
const filteredReports = computed(() => {
  if (!evalData.value) return []
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return evalData.value.reports
  return evalData.value.reports.filter(r => r.doc_name.toLowerCase().includes(kw))
})

// 汇总卡片
const summaryCards = computed(() => {
  if (!evalData.value) return []
  const s = evalData.value.summary
  return [
    { label: 'L1 规则合规', value: s.avg_l1 + '%', percent: s.avg_l1, color: '#3b82f6', icon: '📋', desc: 'Schema 约束检查' },
    { label: 'L2 抽取效率', value: s.avg_l2 + '%', percent: s.avg_l2, color: '#10b981', icon: '🎯', desc: 'ECR/TCR/RCR' },
    { label: 'L3 语义多样性', value: s.avg_l3, percent: s.avg_l3, color: '#f59e0b', icon: '🧬', desc: '信息熵评估' },
    { label: 'L4 LLM 裁判', value: s.avg_l4, percent: s.avg_l4, color: '#8b5cf6', icon: '🏆', desc: '精确/忠实/完整/相关' },
  ]
})

// L2 指标摘要
const l2Summary = computed(() => {
  const r = currentReport.value
  if (!r) return []
  return [
    { label: 'ECR 实体覆盖', value: (r.l2.ecr * 100).toFixed(1) + '%', color: '#3b82f6' },
    { label: 'TCR 三元组覆盖', value: (r.l2.tcr * 100).toFixed(1) + '%', color: '#10b981' },
    { label: 'RCR 关系覆盖', value: (r.l2.rcr * 100).toFixed(1) + '%', color: '#f59e0b' },
  ]
})

// 工具函数
function truncate(str: string, len: number) {
  return str.length > len ? str.substring(0, len) + '...' : str
}

function scoreLevel(score: number) {
  if (score >= 80) return 'score-high'
  if (score >= 65) return 'score-mid'
  return 'score-low'
}

onMounted(async () => {
  try {
    evalData.value = await fetchEvaluationData()
    // 默认选中第一份
    if (evalData.value.reports.length > 0) {
      selectedReportId.value = evalData.value.reports[0].id
    }
  } finally {
    loading.value = false
  }
})

// 切换报告时重绘图表
watch(selectedReportId, () => {
  nextTick(() => renderCharts())
})

// 数据加载后首次渲染
watch(loading, (v) => {
  if (!v && currentReport.value) {
    nextTick(() => renderCharts())
  }
})

function renderCharts() {
  renderRadar()
  renderBar()
  renderPie()
}

function renderRadar() {
  if (!radarChartRef.value || !currentReport.value) return
  if (!radarChart) {
    radarChart = echarts.init(radarChartRef.value)
  }
  const dims = currentReport.value.l4.dimensions
  radarChart.setOption({
    tooltip: { trigger: 'item' },
    radar: {
      indicator: dims.map(d => ({ name: d.name, max: 100 })),
      shape: 'circle',
      splitNumber: 5,
      axisName: { color: '#6b7280', fontSize: 12 },
      splitArea: { areaStyle: { color: ['rgba(59,130,246,0.02)', 'rgba(59,130,246,0.05)'] } },
    },
    series: [{
      type: 'radar',
      data: [{
        value: dims.map(d => d.score),
        name: currentReport.value.doc_name.substring(0, 15),
        areaStyle: { color: 'rgba(59,130,246,0.15)' },
        lineStyle: { color: '#3b82f6', width: 2 },
        itemStyle: { color: '#3b82f6' },
      }],
    }],
  }, true)
}

function renderBar() {
  if (!barChartRef.value || !currentReport.value) return
  if (!barChart) {
    barChart = echarts.init(barChartRef.value)
  }
  const r = currentReport.value
  const breakdown = r.l2.doc_breakdown
  if (breakdown.length === 0) {
    barChart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { top: 20, bottom: 30, left: 50, right: 20 },
      xAxis: { type: 'category', data: ['ECR', 'TCR', 'RCR'], axisLabel: { fontSize: 12 } },
      yAxis: { type: 'value', max: 1, axisLabel: { formatter: (v: number) => (v * 100).toFixed(0) + '%' } },
      series: [{
        type: 'bar',
        data: [
          { value: r.l2.ecr, itemStyle: { color: '#3b82f6' } },
          { value: r.l2.tcr, itemStyle: { color: '#10b981' } },
          { value: r.l2.rcr, itemStyle: { color: '#f59e0b' } },
        ],
        barWidth: 48,
        label: { show: true, position: 'top', formatter: (p: any) => (p.value * 100).toFixed(1) + '%', fontSize: 12, fontWeight: 600 },
      }],
    }, true)
  } else {
    barChart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { bottom: 0, textStyle: { fontSize: 11 } },
      grid: { top: 20, bottom: 40, left: 50, right: 20 },
      xAxis: { type: 'category', data: breakdown.map(d => d.doc_name.length > 8 ? d.doc_name.substring(0, 8) + '...' : d.doc_name), axisLabel: { fontSize: 11 } },
      yAxis: { type: 'value', max: 1, axisLabel: { formatter: (v: number) => (v * 100).toFixed(0) + '%' } },
      series: [
        { name: 'ECR', type: 'bar', data: breakdown.map(d => d.ecr), itemStyle: { color: '#3b82f6' } },
        { name: 'TCR', type: 'bar', data: breakdown.map(d => d.tcr), itemStyle: { color: '#10b981' } },
        { name: 'RCR', type: 'bar', data: breakdown.map(d => d.rcr), itemStyle: { color: '#f59e0b' } },
      ],
    }, true)
  }
}

function renderPie() {
  if (!pieChartRef.value || !currentReport.value) return
  if (!pieChart) {
    pieChart = echarts.init(pieChartRef.value)
  }
  const dist = currentReport.value.l3.type_distribution
  pieChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {d}%' },
    legend: { orient: 'vertical', right: 10, top: 'center', textStyle: { fontSize: 12 } },
    series: [{
      type: 'pie',
      radius: ['35%', '65%'],
      center: ['40%', '50%'],
      data: Object.entries(dist).map(([name, value]) => ({
        name, value,
        itemStyle: { color: getNodeColor(name) },
      })),
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 13, fontWeight: 'bold' } },
    }],
  }, true)
}
</script>

<style scoped lang="scss">
h2 { color: var(--color-text); font-size: 22px; }
h3 { font-size: 16px; color: var(--color-text); margin-bottom: 4px; }

.eval-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  border-top: 4px solid;
  padding: 20px 16px;

  .eval-icon {
    width: 40px;
    height: 40px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    flex-shrink: 0;
  }

  .eval-info {
    flex: 1;
    .eval-score {
      font-size: 28px;
      font-weight: 700;
      line-height: 1.2;
    }
    .eval-label {
      font-size: 13px;
      font-weight: 600;
      color: var(--color-text);
      margin-top: 2px;
    }
    .eval-desc {
      font-size: 12px;
      color: var(--color-text-secondary);
      margin-top: 2px;
    }
  }
}

// Master-Detail 布局
.report-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.report-list-panel {
  width: 280px;
  flex-shrink: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 240px);

  .list-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 16px 0;

    .list-title {
      font-size: 14px;
      font-weight: 600;
      color: var(--color-text);
    }
  }

  // 搜索框留出边距
  :deep(.el-input) {
    margin: 10px 12px !important;
    width: calc(100% - 24px);
  }

  .report-list {
    flex: 1;
    overflow-y: auto;
    padding: 0 8px 8px;

    .report-item {
      padding: 12px;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s;
      margin-bottom: 4px;
      border: 1px solid transparent;

      &:hover {
        background: var(--color-bg-hover, #f5f7fa);
      }

      &.active {
        background: #eff6ff;
        border-color: #3b82f6;
      }

      .item-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;

        .item-name {
          font-size: 13px;
          font-weight: 600;
          color: var(--color-text);
          flex: 1;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .item-score {
          font-size: 16px;
          font-weight: 700;
          flex-shrink: 0;

          &.score-high { color: #10b981; }
          &.score-mid { color: #f59e0b; }
          &.score-low { color: #ef4444; }
        }
      }

      .item-meta {
        margin-top: 4px;

        .item-time {
          font-size: 11px;
          color: var(--color-text-secondary);
        }
      }

      .item-badges {
        display: flex;
        gap: 6px;
        margin-top: 8px;

        .el-tag {
          font-size: 11px;
        }
      }
    }

    .empty-hint {
      text-align: center;
      padding: 24px 0;
      color: var(--color-text-placeholder);
      font-size: 13px;
    }
  }
}

.report-detail-panel {
  flex: 1;
  min-width: 0;

  .detail-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;

    .detail-title-row {
      display: flex;
      align-items: center;
      gap: 12px;
      flex: 1;
      min-width: 0;

      h3 {
        margin: 0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
    }

    .detail-badges {
      display: flex;
      gap: 8px;
      flex-shrink: 0;
    }
  }

  &.empty-detail {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 400px;
  }
}

.empty-placeholder {
  text-align: center;
  color: var(--color-text-placeholder);

  p {
    margin-top: 12px;
    font-size: 14px;
  }
}

.l1-overview {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  font-size: 14px;
  strong { color: #3b82f6; }
}

.l2-metrics {
  display: flex;
  gap: 24px;
  margin-top: 8px;
  .l2-metric-item {
    text-align: center;
    .l2-metric-value {
      display: block;
      font-size: 22px;
      font-weight: 700;
    }
    .l2-metric-label {
      display: block;
      font-size: 12px;
      color: var(--color-text-secondary);
      margin-top: 2px;
    }
  }
}

.l4-dim {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  .l4-label { font-size: 13px; width: 60px; color: var(--color-text-secondary); }
  .l4-score { font-size: 14px; font-weight: 600; width: 40px; text-align: right; }
}

.l4-comment {
  margin-top: 16px;
  padding: 12px 16px;
  background: #f0f9ff;
  border-left: 3px solid #3b82f6;
  border-radius: 0 8px 8px 0;
  .comment-header {
    font-size: 13px;
    font-weight: 600;
    color: #1e40af;
    margin-bottom: 6px;
  }
  .comment-text {
    font-size: 13px;
    line-height: 1.8;
    color: var(--color-text);
  }
}

.l3-entropy {
  .entropy-item {
    display: flex;
    justify-content: space-between;
    padding: 10px 0;
    border-bottom: 1px solid var(--color-border-light);
    .entropy-label { font-size: 13px; color: var(--color-text-secondary); }
    .entropy-value { font-size: 16px; font-weight: 700; color: var(--color-text); }
  }
  .entropy-note {
    margin-top: 12px;
    font-size: 12px;
    color: var(--color-text-placeholder);
    line-height: 1.6;
  }
}
</style>
