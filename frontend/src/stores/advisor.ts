import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AdvisorResult, QueryHistory } from '../types/advisor'

const STORAGE_KEY = 'finpolicy-query-history'

export const useAdvisorStore = defineStore('advisor', () => {
  // 当前查询结果
  const currentResult = ref<AdvisorResult | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const loadingStep = ref(0) // 0-4，表示当前进度阶段
  const loadingMessage = ref('') // 当前进度文字说明

  // 查询历史
  const history = ref<QueryHistory[]>([])

  // 从 localStorage 加载历史
  function loadHistory() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        history.value = JSON.parse(saved)
      }
    } catch {
      // ignore
    }
  }

  // 保存历史到 localStorage
  function saveHistory() {
    try {
      const toSave = history.value.slice(0, 50)
      localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave))
    } catch (e) {
      // 大数据或序列化失败时，只保存摘要不保存完整 result
      try {
        const light = history.value.slice(0, 50).map(h => ({
          ...h,
          result: { query: h.query, matched_policies: [], original_kg_rag_answer: '(数据过大，仅保留摘要)', llm_direct_answer: '' }
        }))
        localStorage.setItem(STORAGE_KEY, JSON.stringify(light))
      } catch {
        // 仍失败则跳过 localStorage 写入
      }
    }
  }

  // 添加查询记录
  function addHistory(query: string, result: AdvisorResult) {
    // 防御：matched_policies 可能不存在或不是数组
    const policies = Array.isArray(result.matched_policies) ? result.matched_policies : []
    const item: QueryHistory = {
      id: Date.now().toString(),
      query,
      timestamp: Date.now(),
      summary: policies.length > 0
        ? `匹配 ${policies.length} 个政策`
        : '未匹配政策',
      result,
    }
    history.value.unshift(item)
    if (history.value.length > 50) {
      history.value = history.value.slice(0, 50)
    }
    saveHistory()
  }

  // 选择历史记录
  function selectHistory(id: string) {
    const item = history.value.find(h => h.id === id)
    if (item?.result) {
      currentResult.value = item.result
    }
  }

  // 清除当前结果，回到初始状态
  function clearResult() {
    currentResult.value = null
    error.value = null
  }

  // 清空历史
  function clearHistory() {
    history.value = []
    saveHistory()
  }

  // 删除单条历史记录
  function removeHistory(id: string) {
    history.value = history.value.filter(h => h.id !== id)
    // 如果当前选中的是这条记录，清除结果
    if (currentResult.value && history.value.find(h => h.id === id)) {
      // noop
    }
    saveHistory()
  }

  // 更新进度
  function updateProgress(step: number, message: string) {
    loadingStep.value = step
    loadingMessage.value = message
  }

  // 重置进度
  function resetProgress() {
    loadingStep.value = 0
    loadingMessage.value = ''
  }

  // 初始化
  loadHistory()

  return {
    currentResult,
    loading,
    error,
    loadingStep,
    loadingMessage,
    history,
    addHistory,
    selectHistory,
    clearResult,
    clearHistory,
    removeHistory,
    updateProgress,
    resetProgress,
  }
})
