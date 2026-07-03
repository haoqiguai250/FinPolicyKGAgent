<template>
  <el-drawer
    v-model="visible"
    :title="title"
    direction="rtl"
    size="420px"
    :before-close="handleClose"
  >
    <div v-if="loading" style="text-align: center; padding: 40px;">
      <el-icon class="is-loading" :size="24"><Loading /></el-icon>
      <p style="margin-top: 8px; color: var(--color-text-secondary);">追溯中...</p>
    </div>

    <div v-else-if="error" class="trace-error">
      <el-icon :size="20" color="#ef4444"><WarningFilled /></el-icon>
      <p>{{ error }}</p>
    </div>

    <div v-else class="trace-content">
      <div v-for="(result, idx) in results" :key="idx" class="trace-item">
        <!-- 溯源路径面包屑 -->
        <div class="trace-breadcrumb">
          <el-tag size="small" type="info">{{ result.source_file.length > 30 ? result.source_file.substring(0, 30) + '...' : result.source_file }}</el-tag>
          <span class="breadcrumb-sep">›</span>
          <span class="breadcrumb-location">{{ result.paragraph_location }}</span>
        </div>

        <!-- 条款范围 -->
        <div v-if="result.clause_range" class="trace-field">
          <span class="field-label">条款范围</span>
          <span class="field-value">{{ result.clause_range }}</span>
        </div>

        <!-- Chunk 原文（带句子高亮） -->
        <div class="trace-field">
          <span class="field-label">政策原文</span>
          <div class="chunk-text" v-html="renderHighlightedText(result)"></div>
        </div>

        <!-- 章节上下文（可折叠） -->
        <el-collapse v-if="result.section_content" class="trace-collapse">
          <el-collapse-item>
            <template #title>
              <span class="collapse-title">📖 章节上下文：{{ result.section_heading }}</span>
            </template>
            <div class="section-text">{{ result.section_content }}</div>
          </el-collapse-item>
        </el-collapse>

        <el-divider v-if="idx < results.length - 1" />
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Loading, WarningFilled } from '@element-plus/icons-vue'
import { traceEntity } from '../api/trace'
import type { TraceResult } from '../types/trace'

const props = defineProps<{
  modelValue: boolean
  entityName: string
  entityType: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
}>()

const visible = ref(false)
const loading = ref(false)
const error = ref('')
const results = ref<TraceResult[]>([])
const title = ref('')

watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val && props.entityName) {
    doTrace()
  }
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

async function doTrace() {
  loading.value = true
  error.value = ''
  results.value = []
  title.value = `📎 溯源：${props.entityName}`

  try {
    results.value = await traceEntity(props.entityName, props.entityType)
    if (results.value.length === 0) {
      error.value = '未找到该实体的原文出处'
    }
  } catch (e: any) {
    error.value = e.message || '追溯失败'
  } finally {
    loading.value = false
  }
}

function handleClose() {
  visible.value = false
}

/**
 * 将 chunk 原文按句拆分，对 sentence_highlights 中的句子高亮
 */
function renderHighlightedText(result: TraceResult): string {
  const text = result.chunk_text || ''
  if (!result.sentence_highlights?.length) {
    return escapeHtml(text)
  }
  const highlights = new Set(result.sentence_highlights)
  const sentences = splitIntoSentences(text)
  return sentences
    .map((s, i) => {
      const idx = i + 1  // 1-based
      if (highlights.has(idx)) {
        return `<span class="sentence-highlight">${escapeHtml(s)}</span>`
      }
      return escapeHtml(s)
    })
    .join('')
}

/** 按中文句末标点拆分句子，同时保留标点 */
function splitIntoSentences(text: string): string[] {
  const parts: string[] = []
  // 匹配：非分隔符 + 分隔符(。！？；\n)
  const re = /[^。！？；\n]+[。！？；\n]/g
  let last = 0
  let match: RegExpExecArray | null
  while ((match = re.exec(text)) !== null) {
    parts.push(match[0])
    last = match.index + match[0].length
  }
  // 剩余未匹配部分（末尾无标点的情况）
  if (last < text.length) {
    parts.push(text.slice(last))
  }
  return parts.length ? parts : [text]
}

/** 防 XSS：转义 HTML 特殊字符 */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}
</script>

<style scoped lang="scss">
.trace-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  background: #fef2f2;
  border-radius: 8px;
  p { color: #991b1b; font-size: 13px; }
}

.trace-content {
  .trace-item {
    .trace-breadcrumb {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 12px;
      flex-wrap: wrap;
      .breadcrumb-sep { color: var(--color-text-secondary); font-size: 12px; }
      .breadcrumb-location { font-size: 13px; color: var(--color-text); font-weight: 500; }
    }

    .trace-field {
      margin-bottom: 12px;
      .field-label {
        display: block;
        font-size: 12px;
        color: var(--color-text-secondary);
        margin-bottom: 4px;
      }
      .field-value {
        font-size: 13px;
        color: var(--color-text);
      }
    }

    .chunk-text {
      background: #f0f9ff;
      border-left: 3px solid #3b82f6;
      padding: 10px 12px;
      border-radius: 0 6px 6px 0;
      font-size: 13px;
      line-height: 1.7;
      color: var(--color-text);

      :deep(.sentence-highlight) {
        background: #fef3c7;
        border-bottom: 2px solid #f59e0b;
        padding: 0 2px;
        border-radius: 2px;
      }
    }

    .trace-collapse {
      border: none;
      margin-top: 8px;

      :deep(.el-collapse-item__header) {
        background: transparent;
        border: none;
        height: 32px;
        line-height: 32px;
      }
      :deep(.el-collapse-item__wrap) {
        border: none;
        background: transparent;
      }

      .collapse-title {
        font-size: 12px;
        color: var(--color-accent);
        cursor: pointer;
      }

      .section-text {
        background: #f9fafb;
        padding: 10px 12px;
        border-radius: 6px;
        font-size: 12px;
        line-height: 1.7;
        color: var(--color-text-secondary);
        max-height: 200px;
        overflow-y: auto;
      }
    }
  }
}
</style>
