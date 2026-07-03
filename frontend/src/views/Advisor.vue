<template>
  <div class="advisor-wrapper">
    <!-- 左侧历史查询栏（联系人风格） -->
    <div class="history-panel">
      <div class="history-header">
        <span>历史查询</span>
        <el-button v-if="advisorStore.history.length > 0" link size="small" type="danger" @click="clearAllHistory">
          清空
        </el-button>
      </div>
      <div class="history-list">
        <div
          v-for="item in advisorStore.history"
          :key="item.id"
          class="history-item"
          :class="{ active: item.id === selectedHistoryId }"
          @click="selectHistory(item.id)"
        >
          <div class="history-icon">💬</div>
          <div class="history-info">
            <div class="history-title">{{ item.query.length > 14 ? item.query.slice(0, 14) + '…' : item.query }}</div>
            <div class="history-desc">{{ item.summary }} · {{ formatTime(item.timestamp) }}</div>
          </div>
          <button class="history-del" @click.stop="confirmDeleteHistory(item.id, item.query)">×</button>
        </div>
        <div v-if="advisorStore.history.length === 0" class="history-empty">
          暂无查询记录
        </div>
      </div>
    </div>

    <!-- 对话区 -->
    <div class="chat-panel">
      <div class="messages-area">
        <!-- ===== 欢迎页（未查询时） ===== -->
        <div v-if="!hasResult && !advisorStore.loading" class="welcome-view">
          <div class="welcome-icon">💬</div>
          <h1 class="welcome-title">Hi，我是 FinPolicyKG</h1>
          <p class="welcome-desc">基于知识图谱的智能政策顾问</p>

          <div class="recommend-cards">
            <div v-for="card in recommendCards" :key="card.label" class="recommend-card" @click="queryInput = card.query; handleQuery()">
              <div class="rc-icon">{{ card.icon }}</div>
              <div class="rc-title">{{ card.label }}</div>
              <div class="rc-desc">{{ card.desc }}</div>
            </div>
          </div>

          <p class="welcome-hint">试试点击卡片，或在下方输入问题</p>
        </div>

        <!-- ===== 加载中 ===== -->
        <div v-if="advisorStore.loading" class="loading-section">
          <div class="loading-spinner">
            <!-- 搜索动画放大镜 -->
            <div class="search-icon-wrap">
              <svg class="search-svg" viewBox="0 0 48 48" width="48" height="48">
                <!-- 镜框 -->
                <circle class="search-ring" cx="20" cy="20" r="12" fill="none" stroke="#3b82f6" stroke-width="2.5" />
                <!-- 手柄 -->
                <line x1="29" y1="29" x2="40" y2="40" stroke="#3b82f6" stroke-width="2.5" stroke-linecap="round" />
                <!-- 扫描光束轨道 -->
                <circle class="scan-arc" cx="20" cy="20" r="12" fill="none" stroke="#3b82f6" stroke-width="1.5"
                  stroke-dasharray="38 38" stroke-dashoffset="0" stroke-linecap="round" opacity="0.6" />
                <!-- 中心光点 -->
                <circle class="scan-dot" cx="20" cy="8" r="2" fill="#3b82f6" opacity="0.8" />
              </svg>
            </div>
            <el-progress
              :percentage="progressPercent"
              :stroke-width="6"
              :show-text="false"
              color="#3b82f6"
              style="max-width: 400px; margin: 0 auto;"
            />
          </div>
          <div class="loading-steps">
            <div
              v-for="(s, i) in progressSteps"
              :key="i"
              class="loading-step"
              :class="{
                'step-done': i < progressStepIndex,
                'step-now': i === progressStepIndex,
                'step-wait': i > progressStepIndex,
              }"
            >
              <div class="step-dot">{{ i < progressStepIndex ? '✓' : i === progressStepIndex ? '●' : '○' }}</div>
              <span class="step-text">{{ s.label }}</span>
            </div>
          </div>
          <p class="loading-msg">{{ progressSteps[progressStepIndex]?.message || '正在处理…' }}</p>
        </div>

        <!-- ===== 错误提示 ===== -->
        <div v-if="advisorStore.error && !advisorStore.loading" class="error-section">
          <div class="error-box">
            <div class="error-icon">!</div>
            <div class="error-content">
              <div class="error-title">查询失败</div>
              <div class="error-message">{{ advisorStore.error }}</div>
            </div>
            <el-button size="small" @click="advisorStore.error = null">知道了</el-button>
          </div>
        </div>

        <!-- ===== 结果展示（双栏对比，非对话式） ===== -->
        <div v-if="advisorStore.currentResult && !advisorStore.loading" class="result-area">
          <!-- 返回按钮 -->
          <div class="result-toolbar">
            <el-button size="small" @click="goBack">← 返回</el-button>
            <span class="result-query-text">{{ selectedHistoryQuery }}</span>
          </div>
          <!-- 企业画像 -->
          <div class="result-card">
            <h3>📋 企业画像识别</h3>
            <div class="profile-tags">
              <el-tag v-if="userProfile?.region" type="success" size="small">地区: {{ userProfile.region }}</el-tag>
              <el-tag v-if="userProfile?.company_type" type="warning" size="small">类型: {{ userProfile.company_type }}</el-tag>
              <el-tag v-if="userProfile?.industry" type="info" size="small">行业: {{ userProfile.industry }}</el-tag>
            </div>
            <p v-if="userProfile?.intent_summary" class="profile-summary">{{ userProfile.intent_summary }}</p>
          </div>

          <!-- 双路对比 -->
          <div class="compare-section">
            <div v-if="kgRagAnswer" class="compare-card kg-card">
              <div class="card-badge badge-kg">
                <el-icon :size="14"><Connection /></el-icon>
                KG-RAG 增强回答
              </div>
              <div class="card-subtitle">基于知识图谱推理生成</div>
              <el-tag v-if="hasFiltered" size="small" type="warning" effect="plain" class="filter-tag">
                已过滤 {{ advisorStore.currentResult!.low_score_nodes.length }} 个低分节点
              </el-tag>
              <div class="compare-content" v-html="renderMarkdown(kgRagAnswer)"></div>
            </div>
            <div class="compare-card llm-card">
              <div class="card-badge badge-llm">
                <el-icon :size="14"><ChatDotSquare /></el-icon>
                LLM 直接回答
              </div>
              <div class="card-subtitle">纯大模型生成（无知识图谱）</div>
              <div class="compare-content" v-html="renderMarkdown(llmDirectAnswer || '')"></div>
            </div>
          </div>

          <!-- 推理子图 -->
          <div v-if="reasoningPaths.length > 0" class="result-card" @click="lockedPathIndex = -1">
            <h3>🕸️ 推理子图
              <el-tag v-if="hasFiltered" size="small" type="warning" effect="plain" style="margin-left: 8px;">
                已过滤后子图（{{ reasoningPaths.length }} 条路径）
              </el-tag>
            </h3>
            <div class="subgraph-wrapper">
              <SubGraph
                :paths="reasoningPaths"
                :perturbation-scores="allPerturbationScores"
                :highlight-path-index="activePathIndex"
                :highlight-node-key="hoveredNodeKey"
                @trace="openTrace"
              />
            </div>
          </div>

          <!-- 推理路径列表 -->
          <div v-if="reasoningPaths.length > 0" class="result-card">
            <h3>🔗 推理路径</h3>
            <div class="path-list" :class="{ collapsed: !showAllPaths }">
              <div
                v-for="(path, idx) in reasoningPaths"
                :key="idx"
                class="path-item"
                :class="{
                  'path-highlighted': hoveredPathIndex === idx || lockedPathIndex === idx,
                  'path-locked': lockedPathIndex === idx,
                }"
                @mouseenter="hoveredPathIndex = idx"
                @mouseleave="hoveredPathIndex = -1"
                @click.stop="lockedPathIndex = lockedPathIndex === idx ? -1 : idx"
              >
                <div class="path-flow">
                  <span class="path-node type-policy" :class="{ 'repealed-policy': path.policy_status === 'repealed' }">{{ path.policy }}</span>
                  <span v-if="path.policy_status === 'repealed'" class="policy-status-tag repealed">已废止</span>
                  <span v-else-if="policyStatusMap[path.policy] === 'expiring_soon'" class="policy-status-tag expiring">即将过期</span>
                  <span class="path-arrow">→ {{ path.provides_raw_relation || 'provides' }} →</span>
                  <span class="path-node type-action">{{ path.action_type }}</span>
                  <span class="path-arrow">→ leads_to →</span>
                  <span class="path-node type-strategy">{{ path.strategies.join(' / ') }}</span>
                </div>
                <div class="path-conditions">
                  <span class="path-label">适用条件:</span>
                  <el-tag v-for="(c, ci) in path.conditions" :key="ci" size="small" type="warning" style="margin: 2px;">{{ c.value }}</el-tag>
                </div>
              </div>
            </div>
            <div v-if="reasoningPaths.length > 3" class="path-toggle" @click="showAllPaths = !showAllPaths">
              <span>{{ showAllPaths ? '收起' : `展开全部（共 ${reasoningPaths.length} 条）` }}</span>
              <el-icon><ArrowDown :class="{ rotated: showAllPaths }" /></el-icon>
            </div>
          </div>

          <!-- 扰动分析 -->
          <div v-if="allPerturbationScores.length > 0" class="result-card">
            <h3>🎯 关键因素分析（KG-PQAM 扰动评分）</h3>
            <p class="section-subtitle">删除单个节点后重新生成回答，对比 4 个维度的指标变化</p>
            <div class="perturbation-list" :class="{ collapsed: !showAllPerturbations }">
              <div
                v-for="(score, idx) in allPerturbationScores"
                :key="idx"
                class="perturbation-item"
                :style="{ borderLeftColor: getPerturbationLevel(score.importance).color }"
                @mouseenter="hoveredNodeKey = `${score.node.name}__${score.node.type}`"
                @mouseleave="hoveredNodeKey = ''"
              >
                <div class="pert-header" @click="togglePerturbationDetail(idx)">
                  <span class="pert-type-badge" :style="{ background: getNodeColor(score.node.type) }">{{ score.node.type }}</span>
                  <span class="pert-name">{{ score.node.name }}</span>
                  <div class="pert-header-right">
                    <el-tag
                      :color="getPerturbationLevel(score.importance).color"
                      effect="dark" size="small"
                      style="color:#fff;border:none;flex-shrink:0;"
                    >
                      {{ getPerturbationLevel(score.importance).label }} {{ (score.importance * 100).toFixed(1) }}%
                    </el-tag>
                    <el-icon class="expand-icon" :class="{ rotated: expandedPerturbations.has(idx) }"><ArrowDown /></el-icon>
                  </div>
                </div>
                <p class="pert-reason">{{ score.reason }}</p>
                <div v-if="expandedPerturbations.has(idx) && score.metric_scores" class="metric-details">
                  <div v-for="(m, mi) in metricLabels" :key="mi" class="metric-row">
                    <span class="metric-label">{{ m.label }}</span>
                    <span class="metric-weight">w={{ (score.metric_scores.weights?.[m.key] || 0.1).toFixed(2) }}</span>
                    <div class="metric-bar">
                      <div class="metric-fill" :style="{ width: ((score.metric_scores[m.key + '_diff'] || score.metric_scores[m.key] || 0) * 100).toFixed(0) + '%', background: m.color }"></div>
                    </div>
                    <span class="metric-value">{{ ((score.metric_scores[m.key + '_diff'] || score.metric_scores[m.key] || 0) * 100).toFixed(0) }}%</span>
                  </div>
                  <div v-if="score.metric_scores.weights?.fallback" class="metric-fallback-note">⚠️ LLM 裁判异常，使用客观指标均分（各 33.3%）</div>
                </div>
                <el-button v-if="score.node.source_chunk_id || score.node.type === 'Policy' || score.node.type === 'Condition'"
                  size="small" type="primary" link style="margin-top:4px;" @click="openTrace(score.node.name, score.node.type)"
                >📎 查看原文出处</el-button>
              </div>
            </div>
            <div v-if="allPerturbationScores.length > 5" class="path-toggle" @click="showAllPerturbations = !showAllPerturbations">
              <span>{{ showAllPerturbations ? '收起' : `展开全部（共 ${allPerturbationScores.length} 条）` }}</span>
              <el-icon><ArrowDown :class="{ rotated: showAllPerturbations }" /></el-icon>
            </div>
          </div>

          <!-- 匹配摘要 -->
          <div v-if="matchedSummary" class="result-card">
            <h3>📊 匹配摘要</h3>
            <div class="match-grid">
              <div class="match-item">
                <span class="match-label">匹配政策</span>
                <div class="match-tags">
                  <el-tag v-for="p in matchedPolicies" :key="p" size="small" type="primary" style="margin:2px;">
                    {{ p.length > 20 ? p.substring(0,20)+'…' : p }}
                  </el-tag>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部输入框（内嵌按钮风格） -->
      <div class="input-bar">
        <div class="input-row">
          <el-input
            v-model="queryInput"
            placeholder="输入政策问题，如「中小企业能享受什么补贴」…"
            size="large"
            @keyup.enter="handleQuery"
            :disabled="advisorStore.loading"
            class="chat-input"
          >
            <template #suffix>
              <el-button
                type="primary"
                @click="handleQuery"
                :loading="advisorStore.loading"
                class="chat-submit"
                :icon="ChatDotSquare"
                circle
              />
            </template>
          </el-input>
        </div>
      </div>
    </div>

    <!-- 追溯面板 -->
    <TracePanel v-model="traceVisible" :entity-name="traceEntityName" :entity-type="traceEntityType" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAdvisorStore } from '../stores/advisor'
import { advise } from '../api/advisor'
import { getPerturbationLevel, getNodeColor } from '../utils/color'
import SubGraph from '../components/SubGraph.vue'
import TracePanel from '../components/TracePanel.vue'
import { Connection, ChatDotSquare, ArrowDown } from '@element-plus/icons-vue'

const advisorStore = useAdvisorStore()
const route = useRoute()
const queryInput = ref('')
const selectedHistoryId = ref<string | null>(null)
const subgraphVisible = ref(true)
const perturbVisible = ref(false)
const policiesVisible = ref(false)
const llmVisible = ref(false)
const showAllPaths = ref(false)
const showAllPerturbations = ref(false)
const expandedPerturbations = ref<Set<number>>(new Set())
const traceVisible = ref(false)
const traceEntityName = ref('')
const traceEntityType = ref('')
const hoveredPathIndex = ref(-1)
const lockedPathIndex = ref(-1)
const hoveredNodeKey = ref('')
const progressStepIndex = ref(0)
let _progressTimer: ReturnType<typeof setInterval> | null = null

const progressSteps = [
  { label: '意图识别', message: '正在解析企业画像，识别查询意图…' },
  { label: '图谱检索', message: '正在检索知识图谱，匹配相关政策…' },
  { label: 'RAG 生成', message: '正在基于图谱生成增强回答…' },
  { label: '扰动分析', message: '正在执行节点扰动测试…' },
  { label: 'LLM 裁判', message: 'LLM 裁判正在评分…' },
  { label: '结果汇总', message: '正在汇总生成最终结果…' },
]

const progressPercent = computed(() =>
  Math.round((progressStepIndex.value / (progressSteps.length - 1)) * 100)
)

const hasResult = computed(() => !!advisorStore.currentResult)

const kgRagAnswer = computed(() => {
  const r = advisorStore.currentResult
  if (!r) return null
  return r.filtered_kg_rag_answer || r.original_kg_rag_answer || (r as any).kg_rag_answer || null
})

const llmDirectAnswer = computed(() => advisorStore.currentResult?.llm_direct_answer || '')

const reasoningPaths = computed(() => {
  const r = advisorStore.currentResult
  if (!r) return []
  if (r.filtered_paths?.length) return r.filtered_paths
  if (r.original_paths?.length) return r.original_paths
  if ((r as any).reasoning_paths?.length) return (r as any).reasoning_paths
  return []
})

const allPerturbationScores = computed(() => {
  const result = advisorStore.currentResult
  if (!result) return []
  const scores: any[] = []
  for (const path of reasoningPaths.value) {
    if (path.perturbation_scores) {
      for (const s of path.perturbation_scores) {
        if (!scores.find(x => x.node.name === s.node.name && x.node.type === s.node.type)) scores.push(s)
      }
    }
  }
  return scores.sort((a, b) => b.importance - a.importance)
})

const activePathIndex = computed(() => (lockedPathIndex.value >= 0 ? lockedPathIndex.value : hoveredPathIndex.value))

const userProfile = computed(() => advisorStore.currentResult?.profile || null)

const matchedSummary = computed(() => {
  const r = advisorStore.currentResult
  return r && r.matched_policies?.length ? true : false
})

const matchedPolicies = computed(() => advisorStore.currentResult?.matched_policies || [])

const policyStatusMap = computed(() => advisorStore.currentResult?.policy_status_map || {})

const recommendCards = [
  { icon: '💰', label: '查资金奖励', desc: '12 条政策', query: '深圳市科技型中小企业有什么资金奖励政策？' },
  { icon: '🏢', label: '查税收优惠', desc: '8 条政策', query: '深圳市科技型中小企业有什么税收优惠政策？' },
  { icon: '🔬', label: '查研发扶持', desc: '6 条政策', query: '深圳市科技型中小企业有什么研发扶持政策？' },
]

function _startProgressSimulation() {
  progressStepIndex.value = 0
  const intervals = [3000, 4000, 5000, 6000, 7000]
  let step = 0
  function tick() {
    step++
    if (step < progressSteps.length) {
      progressStepIndex.value = step
      _progressTimer = setTimeout(tick, intervals[Math.min(step, intervals.length - 1)])
    }
  }
  _progressTimer = setTimeout(tick, intervals[0])
}
function _stopProgressSimulation() {
  if (_progressTimer) { clearTimeout(_progressTimer); _progressTimer = null }
}

async function handleQuery() {
  const query = queryInput.value.trim()
  if (!query || advisorStore.loading) return
  advisorStore.loading = true
  advisorStore.error = null
  advisorStore.clearResult()
  progressStepIndex.value = 0
  _startProgressSimulation()
  // 延迟发起请求，确保 loading 状态已完成 DOM 渲染
  await new Promise(r => setTimeout(r, 50))
  try {
    const result = await advise(query, false)
    advisorStore.currentResult = result
    advisorStore.addHistory(query, result)
    selectedHistoryId.value = advisorStore.history[0]?.id || null
  } catch (e: any) {
    advisorStore.error = e.message || '查询失败'
  } finally {
    _stopProgressSimulation()
    advisorStore.loading = false
  }
}

// 如果 URL 带有 q 参数，自动填入并查询
onMounted(() => {
  const q = route.query.q as string
  if (q) {
    queryInput.value = q
    // 延迟一点让页面先渲染
    setTimeout(() => handleQuery(), 300)
  }
})

function selectHistory(id: string) {
  selectedHistoryId.value = id
  advisorStore.selectHistory(id)
}

function clearAllHistory() {
  advisorStore.clearHistory()
  selectedHistoryId.value = null
}

async function confirmDeleteHistory(id: string, query: string) {
  const { ElMessageBox, ElMessage } = await import('element-plus')
  try {
    await ElMessageBox.confirm(`删除「${query.slice(0, 20)}…」这条记录？`, '确认删除', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    advisorStore.removeHistory(id)
    if (selectedHistoryId.value === id) { selectedHistoryId.value = null; advisorStore.clearResult() }
    ElMessage.success('已删除')
  } catch { /* cancel */ }
}

function openTrace(name: string, type: string) {
  traceEntityName.value = name; traceEntityType.value = type; traceVisible.value = true
}

function goBack() {
  advisorStore.clearResult()
  selectedHistoryId.value = null
}

function togglePerturbationDetail(idx: number) {
  const s = new Set(expandedPerturbations.value)
  if (s.has(idx)) s.delete(idx); else s.add(idx)
  expandedPerturbations.value = s
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  const now = new Date()
  const isToday = d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate()
  const time = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  if (isToday) return time
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${time}`
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + '…' : s
}

function renderMarkdown(text: string): string {
  return text
    .replace(/### (.+)/g, '<h4>$1</h4>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^(\d+)\. (.+)$/gm, '<li class="ol-item">$2</li>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/((?:<li[^>]*>.*?<\/li>\s*)+)/g, '<ul>$1</ul>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br>')
}

const hasFiltered = computed(() => {
  const r = advisorStore.currentResult
  return r && r.low_score_nodes && r.low_score_nodes.length > 0
})

const metricLabels = [
  { key: 'char_overlap', label: '字符重叠差异', color: '#3b82f6' },
  { key: 'entity_retention', label: '实体保留差异', color: '#f59e0b' },
  { key: 'keyword_coverage', label: '关键词覆盖差异', color: '#8b5cf6' },
  { key: 'llm_semantic', label: 'LLM 语义评分', color: '#10b981' },
]

const selectedHistoryQuery = computed(() => {
  if (!selectedHistoryId.value) return ''
  return advisorStore.history.find(h => h.id === selectedHistoryId.value)?.query || ''
})
</script>

<style scoped lang="scss">
.advisor-wrapper {
  display: flex;
  height: 100%;
  overflow: hidden;
}

/* ── 历史查询栏（联系人风格） ── */
.history-panel {
  width: 240px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  padding: 12px 8px;
  overflow-y: auto;

  .history-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 8px 10px;
    font-size: 11px;
    font-weight: 500;
    color: #999;
  }

  .history-list {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .history-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    border-radius: 10px;
    cursor: pointer;
    position: relative;
    transition: background 0.15s;

    &:hover {
      background: #e8e8ea;
      .history-del { opacity: 1; }
    }
    &.active {
      background: #e8e8ea;
      .history-title { font-weight: 600; }
    }

    .history-icon { font-size: 16px; flex-shrink: 0; }
    .history-info {
      flex: 1;
      min-width: 0;
    }
    .history-title {
      font-size: 13px;
      font-weight: 600;
      color: #222;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .history-desc {
      font-size: 11px;
      color: #bbb;
      margin-top: 1px;
    }
    .history-del {
      position: absolute;
      right: 6px;
      top: 4px;
      width: 18px; height: 18px;
      border-radius: 50%;
      border: none;
      background: transparent;
      color: #999;
      font-size: 14px;
      line-height: 1;
      cursor: pointer;
      opacity: 0;
      transition: opacity 0.15s;
      display: flex;
      align-items: center;
      justify-content: center;
      &:hover { background: #ddd; color: #666; }
    }
  }

  .history-empty {
    padding: 32px 8px;
    text-align: center;
    color: #ccc;
    font-size: 12px;
  }
}

/* ── 对话区 ── */
.chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
}

/* ── 欢迎页 ── */
.welcome-view {
  text-align: center;
  padding: 30px 0;
  max-width: 600px;
  margin: 0 auto;

  .welcome-icon {
    width: 56px; height: 56px;
    border-radius: 18px;
    background: #f0f0f0;
    display: flex; align-items: center; justify-content: center;
    font-size: 26px;
    margin: 0 auto 14px;
  }
  .welcome-title { font-size: 20px; font-weight: 500; color: #222; margin-bottom: 6px; }
  .welcome-desc { font-size: 13px; color: #888; margin-bottom: 28px; }
  .welcome-hint { font-size: 12px; color: #ccc; margin-top: 20px; }
}

.recommend-cards {
  display: flex;
  gap: 14px;
  justify-content: center;

  .recommend-card {
    background: white;
    border-radius: 14px;
    padding: 18px 22px;
    width: 160px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    cursor: pointer;
    transition: all 0.15s;
    &:hover {
      box-shadow: 0 4px 12px rgba(0,0,0,0.08);
      transform: translateY(-2px);
    }

    .rc-icon {
      width: 36px; height: 36px;
      border-radius: 10px;
      background: #f0f0f0;
      display: flex; align-items: center; justify-content: center;
      font-size: 18px;
      margin: 0 auto 10px;
    }
    .rc-title { font-size: 14px; font-weight: 500; color: #333; margin-bottom: 3px; }
    .rc-desc { font-size: 11px; color: #999; }
  }
}

/* ── 加载状态 ── */
.loading-section {
  text-align: center;
  padding: 40px 0;

  .loading-spinner {
    margin-bottom: 24px;
    padding: 0 40px;

    .search-icon-wrap {
      display: flex;
      justify-content: center;
      margin-bottom: 20px;

      .search-svg {
        animation: searchPulse 2s ease-in-out infinite;
      }

      .search-ring {
        animation: ringPulse 2s ease-in-out infinite;
      }

      .scan-arc {
        transform-origin: 20px 20px;
        animation: scanRotate 1.8s linear infinite;
      }

      .scan-dot {
        animation: dotMove 1.8s linear infinite;
      }
    }
  }

  @keyframes scanRotate {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  @keyframes dotMove {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  @keyframes ringPulse {
    0%, 100% { opacity: 0.4; }
    50% { opacity: 1; }
  }

  @keyframes searchPulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.08); }
  }

  .loading-steps {
    display: flex;
    justify-content: center;
    gap: 24px;
    margin-bottom: 16px;

    .loading-step {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      color: #ccc;
      &.step-done { color: #999; .step-dot { color: #10b981; } }
      &.step-now { color: #555; font-weight: 500; .step-dot { color: #3b82f6; } }
      &.step-wait { color: #ddd; }
      .step-dot { font-size: 12px; }
    }
  }
  .loading-msg { font-size: 12px; color: #999; }
}

/* ── 错误提示 ── */
.error-section {
  max-width: 600px;
  margin: 40px auto 0;
  text-align: center;

  .error-box {
    display: inline-flex;
    align-items: center;
    gap: 14px;
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 14px;
    padding: 16px 22px;

    .error-icon {
      width: 32px; height: 32px;
      border-radius: 50%;
      background: #ef4444;
      color: #fff;
      display: flex; align-items: center; justify-content: center;
      font-size: 16px; font-weight: 600;
      flex-shrink: 0;
    }
    .error-content { text-align: left; }
    .error-title { font-size: 14px; font-weight: 500; color: #991b1b; }
    .error-message { font-size: 12px; color: #b91c1c; margin-top: 2px; }
  }
}

/* ── 对话气泡 ── */
.chat-messages {
  max-width: 720px;
  margin: 0 auto;
}

.bubble-row {
  margin-bottom: 16px;
  display: flex;

  &.user-row { justify-content: flex-end; }
  &.ai-row { justify-content: flex-start; }
}

.bubble {
  max-width: 75%;
  padding: 10px 16px;
  font-size: 13px;
  line-height: 1.7;
  color: #333;
}

.user-bubble {
  background: #e8f0fe;
  border-radius: 18px 18px 4px 18px;
}

.ai-bubble {
  background: #f0f0f0;
  border-radius: 18px 18px 18px 4px;

  .ai-header {
    font-weight: 500;
    font-size: 12px;
    color: #666;
    margin-bottom: 6px;
  }
  .bubble-content {
    :deep(h4) { font-size: 13px; font-weight: 500; margin: 8px 0 4px; }
    :deep(strong) { font-weight: 500; }
    :deep(ul) { margin: 4px 0; padding-left: 16px; }
    :deep(li) { margin: 2px 0; }
  }
}

/* ── 画像标签 ── */
.profile-tags-row {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
  justify-content: center;
}

/* ── 匹配摘要 ── */
.summary-card {
  background: #f9f9fb;
  border-radius: 14px;
  padding: 14px 18px;
  margin-bottom: 12px;

  .summary-label { font-size: 11px; color: #999; margin-bottom: 8px; font-weight: 500; }
  .summary-tags { display: flex; flex-wrap: wrap; gap: 4px; }
  .summary-tag { font-size: 12px; color: #444; line-height: 1.6; }
}

/* ── 可展开区域 ── */
.extra-section {
  background: white;
  border-radius: 14px;
  padding: 14px 18px;
  margin-bottom: 10px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.03);

  .extra-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 13px;
    font-weight: 500;
    color: #444;
    cursor: pointer;
    user-select: none;

    .toggle-icon { font-size: 11px; color: #999; }
  }

  .subgraph-wrap { margin-top: 12px; }
}

.extra-content {
  font-size: 13px;
  line-height: 1.7;
  color: #555;
  margin-top: 10px;
  padding: 10px 14px;
  background: #f9f9fb;
  border-radius: 10px;
  max-height: 300px;
  overflow-y: auto;

  :deep(h4) { font-size: 13px; font-weight: 500; margin: 8px 0 4px; }
  :deep(strong) { font-weight: 500; }
  :deep(ul) { margin: 4px 0; padding-left: 16px; }
  :deep(li) { margin: 2px 0; }
}

/* ── 扰动分析 ── */
.perturb-list { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }

.perturb-item {
  padding: 10px 14px;
  border-left: 3px solid;
  background: #f9f9fb;
  border-radius: 0 8px 8px 0;

  .perturb-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .perturb-type {
    color: #fff; font-size: 10px; padding: 1px 6px; border-radius: 4px; flex-shrink: 0;
  }
  .perturb-name { font-size: 12px; font-weight: 500; color: #444; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .perturb-reason { font-size: 11px; color: #888; margin-top: 4px; }
}

/* ── 匹配政策 ── */
.policy-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 10px;
  .policy-chip {
    font-size: 11px;
    background: #f0f0f0;
    border-radius: 6px;
    padding: 3px 8px;
    color: #555;
  }
}

/* ── 底部输入框（内嵌按钮风格） ── */
.input-bar {
  padding: 0 28px 18px;
  flex-shrink: 0;

  .input-row {
    max-width: 800px;
    margin: 0 auto;
  }

  .chat-input {
    :deep(.el-input__wrapper) {
      border-radius: 28px;
      border: 1px solid #e0e0e0;
      background: #ffffff;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
      height: 60px;
      padding: 0 8px 0 24px;
      transition: box-shadow 0.2s, border-color 0.2s;

      &:hover {
        border-color: #d0d0d0;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.06);
      }

      &.is-focus {
        border-color: #3b82f6;
        box-shadow: 0 4px 20px rgba(59, 130, 246, 0.10);
      }
    }

    :deep(.el-input__inner) {
      font-size: 15px;
      color: #333;
      height: 60px;
      &::placeholder { color: #bbb; font-size: 14px; }
    }

    :deep(.el-input__suffix) {
      display: flex;
      align-items: center;
      height: 60px;
    }
  }

  .chat-submit {
    width: 42px;
    height: 42px;
    border-radius: 50%;
    border: none;
    font-size: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.20);
    transition: transform 0.15s, box-shadow 0.2s;

    &:hover {
      transform: scale(1.05);
      box-shadow: 0 4px 14px rgba(59, 130, 246, 0.30);
    }

    :deep(.el-icon) {
      font-size: 18px;
    }
  }
}

/* 大屏 ≥ 1680px */
@media screen and (min-width: 1680px) {
  .input-row { max-width: 880px; }
  .result-area { max-width: 960px; }
  .chat-messages { max-width: 860px; }
  .recommend-card { width: 180px; padding: 22px 26px; }
}

/* 超大屏 ≥ 2200px */
@media screen and (min-width: 2200px) {
  .input-row { max-width: 1000px; }
  .result-area { max-width: 1080px; }
  .chat-messages { max-width: 980px; }
}

/* ── 结果展示区 ── */
.result-area {
  max-width: 860px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 14px;

  .result-toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    .result-query-text { font-size: 13px; color: #888; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  }
}

.result-card {
  background: white;
  border-radius: 16px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);

  h3 { font-size: 15px; font-weight: 500; color: #333; margin: 0 0 12px; }
}

.profile-tags { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.profile-summary { margin-top: 8px; font-size: 13px; color: #666; line-height: 1.6; }
.section-subtitle { font-size: 12px; color: #999; margin: -8px 0 12px; }

/* ── 双路对比 ── */
.compare-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.compare-card {
  background: white;
  border-radius: 16px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);

  .card-badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 12px; border-radius: 20px;
    font-size: 13px; font-weight: 500; margin-bottom: 6px;
  }
  .badge-kg { color: #065f46; background: #d1fae5; }
  .badge-llm { color: #374151; background: #f3f4f6; }

  .card-subtitle { font-size: 12px; color: #aaa; margin-bottom: 12px; }
  .filter-tag { margin-bottom: 8px; display: inline-block; }

  .compare-content {
    font-size: 14px; line-height: 1.8; color: #333;
    max-height: 400px; overflow-y: auto;
    :deep(h4) { font-size: 13px; font-weight: 500; margin: 8px 0 4px; }
    :deep(strong) { font-weight: 500; }
    :deep(ul) { margin: 4px 0; padding-left: 16px; }
    :deep(li) { margin: 2px 0; }
  }
}

.kg-card {
  border: 1px solid #d1fae5;
  background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%);
}
.llm-card {
  border: 1px solid #e5e7eb;
  background: linear-gradient(135deg, #f9fafb 0%, #ffffff 100%);
}

/* ── 推理子图 ── */
.subgraph-wrapper { margin-top: 8px; }

/* ── 推理路径 ── */
.path-list {
  display: flex; flex-direction: column; gap: 8px; margin-top: 8px;
  &.collapsed { max-height: 320px; overflow-y: auto; }
}

.path-item {
  padding: 12px 16px; background: #f9f9fb; border-radius: 10px;
  border: 2px solid transparent; transition: all 0.2s; cursor: default;

  &.path-highlighted, &.path-locked {
    border-color: #3b82f6; background: #eff6ff; cursor: pointer;
  }
  &.path-locked::after { content: '📌'; position: absolute; right: 8px; top: 8px; font-size: 12px; opacity: 0.7; }
  position: relative;
}

.path-flow {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px;
  .path-node {
    padding: 4px 10px; border-radius: 6px; font-weight: 500; color: #fff;
    &.type-policy { background: #3b82f6; }
    &.type-action { background: #f97316; }
    &.type-strategy { background: #10b981; }
    // 废止政策灰色+删除线
    &.type-policy.repealed-policy {
      background: #9ca3af;
      text-decoration: line-through;
    }
  }
  .path-arrow { color: #999; font-size: 12px; }
  .policy-status-tag {
    font-size: 10px; padding: 1px 6px; border-radius: 4px; font-weight: 500;
    &.repealed { background: #fee2e2; color: #991b1b; }
    &.expiring { background: #fef3c7; color: #92400e; }
  }
}
.path-conditions { margin-top: 8px; .path-label { font-size: 12px; color: #999; margin-right: 4px; } }

.path-toggle {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  margin-top: 12px; padding: 8px; border-radius: 8px; cursor: pointer;
  font-size: 13px; color: #3b82f6;
  &:hover { background: #f3f4f6; }
}

/* ── 扰动分析 ── */
.perturbation-list {
  display: flex; flex-direction: column; gap: 8px;
  &.collapsed { max-height: 400px; overflow-y: auto; }
}

.perturbation-item {
  padding: 12px 16px; border-left: 4px solid; background: #f9f9fb;
  border-radius: 0 8px 8px 0; transition: all 0.15s;
  &:hover { background: #eff6ff; }

  .pert-header {
    display: flex; align-items: center; gap: 8px; cursor: pointer; user-select: none;
    .pert-type-badge { color: #fff; font-size: 11px; padding: 2px 8px; border-radius: 4px; flex-shrink: 0; }
    .pert-name { font-weight: 500; flex: 1; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .pert-header-right { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
    .expand-icon { font-size: 14px; color: #bbb; transition: transform 0.2s; &.rotated { transform: rotate(180deg); } }
  }
  .pert-reason { margin-top: 6px; font-size: 12px; color: #666; line-height: 1.5; }

  .metric-details {
    margin-top: 12px; padding: 12px; background: #fff; border-radius: 8px; border: 1px solid #f3f4f6;
    .metric-row {
      display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
      .metric-label { font-size: 11px; color: #666; width: 90px; flex-shrink: 0; }
      .metric-weight { font-size: 10px; color: #bbb; width: 38px; flex-shrink: 0; font-family: monospace; }
      .metric-bar { flex: 1; height: 8px; background: #f3f4f6; border-radius: 4px; overflow: hidden; .metric-fill { height: 100%; border-radius: 4px; transition: width 0.4s; } }
      .metric-value { width: 36px; text-align: right; font-size: 11px; font-weight: 600; color: #333; font-family: monospace; }
    }
    .metric-fallback-note { margin-top: 8px; padding: 6px 10px; background: #fffbeb; border-radius: 4px; font-size: 11px; color: #92400e; }
  }
}

/* ── 匹配摘要 ── */
.match-grid {
  .match-item {
    .match-label { font-size: 12px; color: #999; display: block; margin-bottom: 6px; }
    .match-tags { display: flex; flex-wrap: wrap; gap: 4px; }
  }
}
</style>
