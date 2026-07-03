import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { GraphData, KGStats } from '../types/kg'

export const useKGStore = defineStore('kg', () => {
  const graphData = ref<GraphData | null>(null)
  const stats = ref<KGStats | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 筛选状态
  const activeTypes = ref<string[]>(['Policy', 'Condition', 'ActionType', 'Strategy', 'Company'])
  const searchKeyword = ref('')

  // 选中节点
  const selectedNodeId = ref<string | null>(null)

  function toggleType(type: string) {
    const idx = activeTypes.value.indexOf(type)
    if (idx >= 0) {
      activeTypes.value.splice(idx, 1)
    } else {
      activeTypes.value.push(type)
    }
  }

  return {
    graphData,
    stats,
    loading,
    error,
    activeTypes,
    searchKeyword,
    selectedNodeId,
    toggleType,
  }
})
