<template>
  <div class="push-records-page">
    <div class="page-header">
      <div class="page-title">
        <h1>推送记录</h1>
        <p class="page-desc">查看定时自动推送的政策匹配历史</p>
      </div>
      <div class="page-controls">
        <el-date-picker
          v-model="selectedDate"
          type="date"
          placeholder="选择日期"
          format="YYYY-MM-DD"
          value-format="YYYYMMDD"
          :clearable="true"
          @change="onDateChange"
        />
        <el-button size="default" @click="refresh" :loading="refreshing">
          ↻ 刷新
        </el-button>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="initialLoading" class="loading-state">
      <div v-for="i in 3" :key="i" class="card" style="margin-bottom: 16px;">
        <el-skeleton :rows="4" animated />
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else-if="records.length === 0" class="empty-state card">
      <div class="empty-icon">📭</div>
      <h3>暂无推送记录</h3>
      <p>定时推送任务执行后，记录将显示在这里</p>
    </div>

    <!-- 记录列表 -->
    <div v-else class="records-list">
      <div class="records-count">共 {{ total }} 条推送记录</div>
      <div
        v-for="(record, idx) in records"
        :key="idx"
        class="record-card card"
        :class="record.has_match ? 'matched' : 'no-match'"
      >
        <!-- 卡片头部 -->
        <div class="card-header" @click="toggleExpand(idx)">
          <div class="header-left">
            <span class="status-dot" :class="record.has_match ? 'dot-matched' : 'dot-no-match'" />
            <span class="push-time">{{ record.push_time }}</span>
            <el-tag
              v-if="record.has_match"
              size="small"
              type="success"
              effect="dark"
            >
              ✅ 匹配 {{ record.matched_policies.length }} 条
            </el-tag>
            <el-tag v-else size="small" type="info" effect="plain">
              ❌ 无匹配
            </el-tag>
            <el-tag v-if="record.new_policies_count > 0" size="small" type="warning">
              🆕 新政策 {{ record.new_policies_count }}
            </el-tag>
          </div>
          <div class="header-right">
            <span class="source-badge" :class="'source-' + record.source">
              {{ record.source === 'both' ? 'KG + LLM' : record.source === 'llm_direct' ? '仅 LLM' : '仅 KG' }}
            </span>
            <el-icon class="expand-icon" :class="{ rotated: expandedIndices.has(idx) }">
              <ArrowDown />
            </el-icon>
          </div>
        </div>

        <!-- 折叠详情 -->
        <div v-if="expandedIndices.has(idx)" class="card-body">
          <!-- 企业画像 -->
          <div class="detail-section">
            <h4>企业画像</h4>
            <div class="profile-tags">
              <el-tag size="small" type="success">{{ record.profile.region }}</el-tag>
              <el-tag size="small" type="warning">{{ record.profile.company_type }}</el-tag>
              <el-tag size="small" type="info">{{ record.profile.industry }}</el-tag>
              <el-tag v-if="record.profile.extra_note" size="small">{{ record.profile.extra_note }}</el-tag>
            </div>
          </div>

          <!-- 查询 -->
          <div class="detail-section">
            <h4>查询</h4>
            <p class="query-text">{{ record.query }}</p>
          </div>

          <!-- 匹配政策 -->
          <div v-if="record.matched_policies.length > 0" class="detail-section">
            <h4>匹配政策（{{ record.matched_policies.length }} 条）</h4>
            <ul class="policy-list">
              <li v-for="(policy, pi) in record.matched_policies" :key="pi">{{ policy }}</li>
            </ul>
          </div>

          <!-- 废止标注（P3 时序化） -->
          <div v-if="record.repealed_notes && record.repealed_notes.length > 0" class="detail-section repealed-section">
            <h4>⚠️ 相关政策已废止</h4>
            <div v-for="(note, ni) in record.repealed_notes" :key="ni" class="repealed-note">
              <span class="repealed-policy">{{ note.repealed_policy }}</span>
              <span class="repealed-info">已于 {{ note.replaced_by ? '' : note.repealed_at }} 废止</span>
              <span v-if="note.replaced_by" class="replaced-by">→ 替代政策：{{ note.replaced_by }}</span>
            </div>
          </div>

          <!-- LLM 回答 -->
          <div v-if="record.llm_direct_answer" class="detail-section">
            <h4>📄 LLM 回答</h4>
            <div class="llm-answer" v-html="renderMarkdown(record.llm_direct_answer)"></div>
          </div>

          <!-- KG-RAG 回答 -->
          <div v-if="record.kg_rag_answer" class="detail-section">
            <h4>🧠 KG-RAG 回答</h4>
            <div class="llm-answer" v-html="renderMarkdown(record.kg_rag_answer)"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import type { PushRecord } from '../types/push'
import { fetchPushRecords } from '../api/push'

const records = ref<PushRecord[]>([])
const total = ref(0)
const initialLoading = ref(true)
const refreshing = ref(false)
const selectedDate = ref<string | null>(null)
const expandedIndices = ref<Set<number>>(new Set())

onMounted(async () => {
  await loadRecords()
  initialLoading.value = false
})

async function loadRecords() {
  try {
    const result = await fetchPushRecords(selectedDate.value || undefined)
    records.value = result.records
    total.value = result.total
  } catch {
    // Error handled silently for now
  }
}

async function refresh() {
  refreshing.value = true
  await loadRecords()
  refreshing.value = false
}

function onDateChange() {
  expandedIndices.value = new Set()
  loadRecords()
}

function toggleExpand(idx: number) {
  const next = new Set(expandedIndices.value)
  if (next.has(idx)) {
    next.delete(idx)
  } else {
    next.add(idx)
  }
  expandedIndices.value = next
}

// Markdown 渲染（与 Advisor.vue 一致）
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
</script>

<style scoped lang="scss">
.push-records-page {
  max-width: 860px;
  margin: 0 auto;
  padding: var(--spacing-lg);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-lg);
  flex-wrap: wrap;
  gap: 12px;

  .page-title h1 {
    font-size: 22px;
    font-weight: 700;
    color: var(--color-text-primary);
    margin: 0;
  }
  .page-desc {
    color: var(--color-text-secondary);
    font-size: 14px;
    margin-top: 6px;
  }
  .page-controls {
    display: flex;
    gap: 8px;
    align-items: center;
  }
}

.card {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
  box-shadow: var(--shadow-sm);
}

.loading-state {
  margin-top: 8px;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  .empty-icon { font-size: 48px; margin-bottom: 12px; }
  h3 { font-size: 16px; color: var(--color-text-primary); margin: 0 0 6px; }
  p { color: var(--color-text-secondary); font-size: 14px; margin: 0; }
}

.records-count {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 12px;
}

.record-card {
  margin-bottom: 12px;
  padding: 0;
  overflow: hidden;
  transition: box-shadow 0.2s;

  &.matched { border-left: 4px solid var(--color-success); }
  &.no-match { border-left: 4px solid #d1d5db; }
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  cursor: pointer;
  transition: background 0.15s;
  user-select: none;

  &:hover { background: #f8fafc; }

  .header-left {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
    &.dot-matched { background: var(--color-success); }
    &.dot-no-match { background: #d1d5db; }
  }

  .push-time {
    font-size: 14px;
    font-weight: 500;
    color: var(--color-text-primary);
    white-space: nowrap;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .source-badge {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 500;
    &.source-both { background: #dbeafe; color: #1d4ed8; }
    &.source-llm_direct { background: #f3f4f6; color: #6b7280; }
    &.source-kg_rag { background: #d1fae5; color: #047857; }
  }

  .expand-icon {
    font-size: 14px;
    transition: transform 0.2s;
    color: var(--color-text-secondary);
    &.rotated { transform: rotate(180deg); }
  }
}

.card-body {
  border-top: 1px solid var(--color-border);
  padding: 16px;
}

.detail-section {
  margin-bottom: 16px;
  &:last-child { margin-bottom: 0; }

  h4 {
    font-size: 13px;
    font-weight: 600;
    color: var(--color-text-secondary);
    margin: 0 0 8px;
  }
}

.profile-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.query-text {
  font-size: 13px;
  color: var(--color-text-primary);
  background: #f8fafc;
  padding: 8px 12px;
  border-radius: 6px;
  margin: 0;
  font-family: monospace;
}

.policy-list {
  margin: 0;
  padding-left: 20px;
  li {
    font-size: 13px;
    color: var(--color-text-primary);
    padding: 2px 0;
    line-height: 1.5;
  }
}

.repealed-section {
  h4 { color: #991b1b !important; }
  .repealed-note {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    background: #fef2f2;
    border-radius: 6px;
    margin-bottom: 6px;
    font-size: 12px;
    &:last-child { margin-bottom: 0; }
    .repealed-policy {
      font-weight: 600;
      color: #991b1b;
      text-decoration: line-through;
    }
    .repealed-info { color: #b91c1c; }
    .replaced-by { color: #1d4ed8; font-weight: 500; }
  }
}

.llm-answer {
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text-primary);
  background: #f8fafc;
  padding: 12px 16px;
  border-radius: 6px;
  max-height: 400px;
  overflow-y: auto;

  :deep(h4) {
    font-size: 14px;
    font-weight: 600;
    color: #1e293b;
    margin: 12px 0 6px;
  }
  :deep(strong) { font-weight: 600; }
  :deep(ul) { margin: 4px 0; padding-left: 20px; }
  :deep(li) { font-size: 13px; line-height: 1.6; }
}
</style>
