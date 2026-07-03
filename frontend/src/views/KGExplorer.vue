<template>
  <div class="kg-page">
    <!-- 顶部筛选栏 -->
    <div class="kg-toolbar card">
      <div class="filter-group">
        <span class="filter-label">类型筛选:</span>
        <el-check-tag
          v-for="type in allTypes"
          :key="type"
          :checked="kgStore.activeTypes.includes(type)"
          @change="kgStore.toggleType(type)"
          :style="{ '--tag-color': getNodeColor(type) }"
          class="type-filter-tag"
        >
          <span class="dot" :style="{ background: getNodeColor(type) }"></span>
          {{ type }}
        </el-check-tag>
      </div>
      <div class="search-group">
        <el-input v-model="kgStore.searchKeyword" placeholder="搜索节点..." size="small" clearable style="width: 200px;" />
        <span class="node-count" v-if="graphDataLoaded">{{ filteredCount }} 个节点</span>
      </div>
    </div>

    <!-- 主区域：图谱 + 信息卡 -->
    <div class="kg-main">
      <div class="kg-canvas" ref="canvasRef">
        <!-- 加载态 -->
        <div v-if="!graphDataLoaded" class="kg-loading">
          <el-icon class="is-loading" :size="32"><Loading /></el-icon>
          <p>加载知识图谱数据...</p>
        </div>

        <!-- 节点信息卡（固定右上角，悬停和点击共用） -->
        <div
          v-if="tooltip.visible"
          class="node-tooltip"
        >
          <div class="tooltip-header">
            <span class="tooltip-type-badge" :style="{ background: getNodeColor(tooltip.type) }">{{ tooltip.type }}</span>
            <span class="tooltip-name">{{ tooltip.name }}</span>
            <span class="tooltip-close" @click="closeTooltip">✕</span>
          </div>
          <div class="tooltip-relations" v-if="tooltip.relations.length > 0">
            <span class="tooltip-label">关联关系</span>
            <div v-for="(r, i) in tooltip.relations.slice(0, 8)" :key="i" class="tooltip-rel-item">
              <span class="rel-arrow">{{ r.direction }}</span>
              <span class="rel-label">{{ r.relation }}</span>
              <span class="rel-target">{{ r.target }}</span>
            </div>
            <div v-if="tooltip.relations.length > 8" class="tooltip-more">+{{ tooltip.relations.length - 8 }} 条</div>
          </div>
          <div class="tooltip-props" v-if="tooltip.properties && Object.keys(filteredTooltipProps).length > 0">
            <span class="tooltip-label">节点属性</span>
            <div v-for="(val, key) in filteredTooltipProps" :key="key" class="tooltip-prop-item">
              <span class="prop-key">{{ key }}</span>
              <span class="prop-value">{{ formatPropValue(val) }}</span>
            </div>
          </div>
          <div class="tooltip-action" @click="handleTooltipTrace">📎 查看原文出处</div>
        </div>
      </div>
    </div>

    <!-- 图例 -->
    <div class="kg-legend">
      <span v-for="type in allTypes" :key="type" class="legend-item">
        <span class="dot" :style="{ background: getNodeColor(type) }"></span>
        {{ type }}
      </span>
      <span class="legend-hint">滚轮缩放 · 拖拽平移 · 点击节点查看详情</span>
    </div>

    <!-- 全链路追溯面板 -->
    <TracePanel
      v-model="traceVisible"
      :entity-name="traceEntityName"
      :entity-type="traceEntityType"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import * as d3 from 'd3'
import { Loading } from '@element-plus/icons-vue'
import { useKGStore } from '../stores/kg'
import { fetchGraphData } from '../api/kg'
import { getNodeColor } from '../utils/color'
import type { KGNode, KGEdge } from '../types/kg'
import TracePanel from '../components/TracePanel.vue'

const kgStore = useKGStore()
const canvasRef = ref<HTMLElement>()
const graphDataLoaded = ref(false)
const filteredCount = ref(0)

// 追溯状态
const traceVisible = ref(false)
const traceEntityName = ref('')
const traceEntityType = ref('')

// 信息卡状态
const tooltip = reactive({
  visible: false,
  locked: false,
  name: '',
  type: '',
  properties: {} as Record<string, unknown>,
  relations: [] as { direction: string, relation: string, target: string }[]
})
// 保存当前图数据引用，tooltip 用
let currentEdges: KGEdge[] = []
let currentNodes: KGNode[] = []

// D3 引用
let currentLinkLabels: d3.Selection<SVGTextElement, KGEdge, SVGGElement, unknown> | null = null
let currentNodesSelection: d3.Selection<SVGGElement, KGNode, SVGGElement, unknown> | null = null

function showTooltipForNode(event: MouseEvent, d: KGNode) {
  tooltip.name = d.name
  tooltip.type = d.type
  tooltip.properties = d.properties || {}
  tooltip.relations = getNodeRelationsForTooltip(d.id)
  tooltip.visible = true
}

// 当前锁定的节点 id（点击锁定，再次点击取消）
const selectedNodeId = ref('')

function closeTooltip() {
  tooltip.visible = false
  tooltip.locked = false
  selectedNodeId.value = ''
}

// 工具提示属性过滤（跳过内部字段）
const SYSTEM_KEYS = new Set(['name', 'entity_type', 'source_chunk_id', 'source_file'])
const filteredTooltipProps = computed(() => {
  const props: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(tooltip.properties)) {
    if (!SYSTEM_KEYS.has(k) && v !== null && v !== undefined && v !== '') {
      props[k] = v
    }
  }
  return props
})

function formatPropValue(val: unknown): string {
  if (Array.isArray(val)) return val.join(', ')
  if (typeof val === 'object' && val !== null) return JSON.stringify(val)
  return String(val)
}

function getNodeRelationsForTooltip(nodeId: string): { direction: string, relation: string, target: string }[] {
  const rels: { direction: string, relation: string, target: string }[] = []
  for (const e of currentEdges) {
    const s = typeof e.source === 'string' ? e.source : (e.source as KGNode).id
    const t = typeof e.target === 'string' ? e.target : (e.target as KGNode).id
    // 优先展示原始关系名（如"补贴"），否则展示归一化关系名
    const relLabel = e.properties?.raw_relation || e.relation
    if (s === nodeId) {
      const tgtNode = currentNodes.find(n => n.id === t)
      rels.push({ direction: '→', relation: relLabel as string, target: tgtNode?.name || t })
    } else if (t === nodeId) {
      const srcNode = currentNodes.find(n => n.id === s)
      rels.push({ direction: '←', relation: relLabel as string, target: srcNode?.name || s })
    }
  }
  return rels
}

function handleTooltipTrace() {
  traceEntityName.value = tooltip.name
  traceEntityType.value = tooltip.type
  traceVisible.value = true
  closeTooltip()
}

const allTypes = ['Policy', 'Condition', 'ActionType', 'Strategy', 'Company']

let simulation: d3.Simulation<KGNode, KGEdge> | null = null
let svg: d3.Selection<SVGSVGElement, unknown, null, undefined> | null = null

onMounted(async () => {
  const data = await fetchGraphData()
  kgStore.graphData = data
  graphDataLoaded.value = true
  renderGraph(data)
})

// 类型筛选变化
watch(() => kgStore.activeTypes, () => {
  if (kgStore.graphData) {
    renderGraph(kgStore.graphData)
  }
})

// 搜索关键词变化 → 高亮匹配节点
watch(() => kgStore.searchKeyword, (keyword) => {
  if (!currentNodesSelection) return
  const kw = keyword.trim().toLowerCase()

  currentNodesSelection.select('circle')
    .transition().duration(200)
    .attr('opacity', () => {
      if (!kw) return 1
      return 1
    })
    .attr('stroke-width', (d: any) => {
      if (!kw) return 2
      return d.name.toLowerCase().includes(kw) ? 4 : 1.5
    })
    .attr('stroke', (d: any) => {
      if (!kw) return '#fff'
      return d.name.toLowerCase().includes(kw) ? '#1d4ed8' : '#e5e7eb'
    })

  currentNodesSelection.select('text')
    .transition().duration(200)
    .attr('font-weight', (d: any) => {
      if (!kw) return 500
      return d.name.toLowerCase().includes(kw) ? 700 : 400
    })
    .attr('opacity', (d: any) => {
      if (!kw) return 1
      return d.name.toLowerCase().includes(kw) ? 1 : 0.3
    })

  // 更新计数
  if (kw && currentNodes.length > 0) {
    filteredCount.value = currentNodes.filter(n => n.name.toLowerCase().includes(kw)).length
  } else {
    filteredCount.value = currentNodes.length
  }
})

function renderGraph(data: { nodes: KGNode[], edges: KGEdge[] }) {
  if (!canvasRef.value) return

  d3.select(canvasRef.value).selectAll('svg').remove()

  const width = canvasRef.value.clientWidth
  const height = canvasRef.value.clientHeight

  const visibleNodeIds = new Set(
    data.nodes.filter(n => kgStore.activeTypes.includes(n.type)).map(n => n.id)
  )
  const visibleNodes = data.nodes.filter(n => visibleNodeIds.has(n.id))

  const visibleEdges = data.edges
    .filter(e => {
      const src = typeof e.source === 'string' ? e.source : (e.source as KGNode).id
      const tgt = typeof e.target === 'string' ? e.target : (e.target as KGNode).id
      return visibleNodeIds.has(src) && visibleNodeIds.has(tgt)
    })
    .map(e => ({
      ...e,
      source: typeof e.source === 'string' ? e.source : (e.source as KGNode).id,
      target: typeof e.target === 'string' ? e.target : (e.target as KGNode).id,
    }))

  // 保存引用给 tooltip 用
  currentNodes = visibleNodes
  currentEdges = visibleEdges
  filteredCount.value = visibleNodes.length

  svg = d3.select(canvasRef.value)
    .append('svg')
    .attr('width', width)
    .attr('height', height)

  const g = svg.append('g')

  const zoom = d3.zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.3, 5])
    .on('zoom', (event) => {
      g.attr('transform', event.transform)
    })
  svg.call(zoom)

  simulation = d3.forceSimulation(visibleNodes as d3.SimulationNodeDatum[])
    .force('link', d3.forceLink(visibleEdges).id((d: any) => d.id).distance(140))
    .force('charge', d3.forceManyBody().strength(-400))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(40))

  const link = g.append('g')
    .selectAll('line')
    .data(visibleEdges)
    .join('line')
    .attr('stroke', '#c4c9d4')
    .attr('stroke-width', 1.5)
    // 边样式按 source 区分：extraction/normalized 实线，auto_promoted/pool_backfill 虚线，truncated 点线
    .attr('stroke-dasharray', (d: any) => {
      const src = d.properties?.source
      if (src === 'auto_promoted' || src === 'pool_backfill') return '6 3'
      if (src === 'truncated') return '2 3'
      return 'none'
    })

  // 边标签（关系名）— 优先展示 raw_relation
  currentLinkLabels = g.append('g')
    .selectAll('text')
    .data(visibleEdges)
    .join('text')
    .text((d: any) => d.properties?.raw_relation || d.relation)
    .attr('font-size', 9)
    .attr('fill', '#6b7280')
    .attr('text-anchor', 'middle')
    .attr('dy', -4)
    .attr('paint-order', 'stroke')
    .attr('stroke', '#ffffff')
    .attr('stroke-width', 3)
    .attr('stroke-opacity', 0.8)

  const node = g.append('g')
    .selectAll('g')
    .data(visibleNodes)
    .join('g')
    .call(d3.drag<SVGGElement, KGNode>()
      .on('start', (event, d) => {
        if (!event.active) simulation?.alphaTarget(0.3).restart()
        d.fx = d.x; d.fy = d.y
      })
      .on('drag', (event, d) => {
        d.fx = event.x; d.fy = event.y
      })
      .on('end', (event, d) => {
        if (!event.active) simulation?.alphaTarget(0)
        d.fx = null; d.fy = null
      })
    )

  currentNodesSelection = node

  function getNodeRadius(d: KGNode): number {
    const edgeCount = visibleEdges.filter(e => {
      const src = typeof e.source === 'string' ? e.source : (e.source as KGNode).id
      const tgt = typeof e.target === 'string' ? e.target : (e.target as KGNode).id
      return src === d.id || tgt === d.id
    }).length
    return Math.max(16, Math.min(28, 14 + edgeCount * 3))
  }

  // 节点圆（SubGraph 风格：半透明填充 + 类型色边框）
  node.append('circle')
    .attr('r', (d) => getNodeRadius(d))
    .attr('fill', (d) => getNodeColor(d.type) + '30')
    .attr('stroke', (d) => getNodeColor(d.type))
    .attr('stroke-width', 2)
    .style('cursor', 'pointer')

  // 节点标签
  node.append('text')
    .text((d) => d.name.length > 12 ? d.name.substring(0, 12) + '...' : d.name)
    .attr('dx', (d) => getNodeRadius(d) + 6)
    .attr('dy', 4)
    .attr('font-size', 11)
    .attr('font-weight', 500)
    .attr('fill', '#1f2937')
    .attr('paint-order', 'stroke')
    .attr('stroke', '#ffffff')
    .attr('stroke-width', 3)
    .attr('stroke-opacity', 0.9)

  // 点击节点 → 锁定/取消信息卡
  node.on('click', (event, d) => {
    event.stopPropagation()
    if (selectedNodeId.value === d.id) {
      // 再次点击同一个节点 → 解除锁定
      selectedNodeId.value = ''
      tooltip.locked = false
      tooltip.visible = false
    } else {
      // 锁定并显示当前节点
      selectedNodeId.value = d.id
      tooltip.locked = true
      showTooltipForNode(event, d)
    }
  })

  // 悬停：只高亮边框，不改变信息卡（锁定状态下完全不干扰）
  node.on('mouseenter', function(event: MouseEvent, d: KGNode) {
    d3.select(this).select('circle').attr('stroke-width', 4)
    if (!tooltip.locked) {
      showTooltipForNode(event, d)
    }
  }).on('mouseleave', function() {
    d3.select(this).select('circle').attr('stroke-width', 2)
    if (!tooltip.locked) {
      tooltip.visible = false
    }
  })

  // 仿真 tick
  simulation.on('tick', () => {
    link
      .attr('x1', (d: any) => d.source.x)
      .attr('y1', (d: any) => d.source.y)
      .attr('x2', (d: any) => d.target.x)
      .attr('y2', (d: any) => d.target.y)

    // 边标签定位在中间
    currentLinkLabels
      ?.attr('x', (d: any) => (d.source.x + d.target.x) / 2)
      .attr('y', (d: any) => (d.source.y + d.target.y) / 2)

    node.attr('transform', (d: any) => `translate(${d.x},${d.y})`)
  })

  // 点击空白关闭 tooltip
  svg.on('click', () => {
    selectedNodeId.value = ''
    tooltip.locked = false
    tooltip.visible = false
  })
}
</script>

<style scoped lang="scss">
.kg-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--header-height));
}

.kg-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-radius: 0;
  border-bottom: 1px solid var(--color-border);

  .filter-group {
    display: flex;
    align-items: center;
    gap: 8px;
    .filter-label { font-size: 13px; color: var(--color-text-secondary); margin-right: 4px; }
  }
  .search-group {
    display: flex;
    align-items: center;
    gap: 8px;
    .node-count { font-size: 12px; color: var(--color-text-placeholder); }
  }
}

.type-filter-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  .dot { width: 8px; height: 8px; border-radius: 50%; }
}

.kg-main {
  flex: 1;
  display: flex;
  position: relative;
  overflow: hidden;
}

.kg-canvas {
  flex: 1;
  background: #fafbfc;
  position: relative;
}

.kg-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: var(--color-text-secondary);
  p { margin-top: 8px; font-size: 13px; }
}

// 悬停信息卡（固定右上角）
.node-tooltip {
  position: absolute;
  z-index: 100;
  right: 16px;
  top: 16px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  border: 1px solid #e5e7eb;
  padding: 12px 14px;
  min-width: 180px;
  max-width: 260px;
  font-size: 12px;

  .tooltip-header {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 8px;
    .tooltip-type-badge {
      color: #fff;
      font-size: 10px;
      padding: 1px 6px;
      border-radius: 4px;
      white-space: nowrap;
    }
    .tooltip-name {
      font-weight: 600;
      color: #1f2937;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      flex: 1;
    }
    .tooltip-close {
      color: #9ca3af;
      cursor: pointer;
      font-size: 14px;
      line-height: 1;
      &:hover { color: #374151; }
    }
  }

  .tooltip-label {
    display: block;
    font-size: 11px;
    color: #9ca3af;
    margin-bottom: 4px;
  }

  .tooltip-relations {
    margin-bottom: 8px;
    .tooltip-rel-item {
      display: flex;
      align-items: center;
      gap: 4px;
      padding: 2px 0;
      font-size: 11px;
      .rel-arrow { color: #9ca3af; }
      .rel-label { color: #6b7280; }
      .rel-target {
        color: #3b82f6;
        font-weight: 500;
        cursor: pointer;
        &:hover { text-decoration: underline; }
      }
    }
    .tooltip-more {
      font-size: 11px;
      color: #9ca3af;
      margin-top: 2px;
    }
  }

  .tooltip-props {
    margin-bottom: 8px;
    .tooltip-prop-item {
      display: flex;
      gap: 8px;
      padding: 2px 0;
      font-size: 11px;
      .prop-key {
        color: #6b7280;
        min-width: 80px;
        word-break: break-all;
      }
      .prop-value {
        color: #059669;
        font-weight: 500;
        word-break: break-all;
      }
    }
  }

  .tooltip-action {
    margin-top: 6px;
    padding-top: 8px;
    border-top: 1px solid #f3f4f6;
    color: #3b82f6;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    &:hover {
      color: #2563eb;
      text-decoration: underline;
    }
  }
}

.kg-legend {
  display: flex;
  gap: 16px;
  padding: 8px 16px;
  background: var(--color-card);
  border-top: 1px solid var(--color-border);
  font-size: 12px;
  color: var(--color-text-secondary);
  align-items: center;
  .legend-item {
    display: flex;
    align-items: center;
    gap: 4px;
    .dot { width: 10px; height: 10px; border-radius: 50%; }
  }
  .legend-hint {
    margin-left: auto;
    font-size: 11px;
    color: var(--color-text-placeholder);
  }
}
</style>
