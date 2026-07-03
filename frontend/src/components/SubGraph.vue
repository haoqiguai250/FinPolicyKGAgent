<template>
  <div class="subgraph-container" ref="containerRef">
    <!-- 悬停信息卡（固定右上角） -->
    <div
      v-if="tooltip.visible"
      class="node-tooltip"
    >
      <div class="tooltip-header">
        <span class="tooltip-type-badge" :style="{ background: getNodeColor(tooltip.type) }">{{ tooltip.type }}</span>
        <span class="tooltip-name">{{ tooltip.name }}</span>
        <span class="tooltip-close" @click="closeTooltip">✕</span>
      </div>
      <div v-if="tooltip.importance > 0" class="tooltip-importance">
        <span class="tooltip-label">重要程度</span>
        <div class="tooltip-bar-track">
          <div class="tooltip-bar-fill" :style="{ width: (tooltip.importance * 100) + '%', background: getPerturbationLevel(tooltip.importance).color }"></div>
        </div>
        <span class="tooltip-value">{{ (tooltip.importance * 100).toFixed(1) }}%</span>
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
      <div class="tooltip-action" @click="handleTrace">📎 查看原文出处</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import * as d3 from 'd3'
import { getNodeColor, getPerturbationLevel } from '../utils/color'
import type { ReasoningPath, PerturbationScore } from '../types/advisor'

const props = defineProps<{
  paths: ReasoningPath[]
  perturbationScores?: PerturbationScore[]
  highlightPathIndex?: number
  highlightNodeKey?: string
}>()

const emit = defineEmits<{
  (e: 'trace', name: string, type: string): void
}>()

const containerRef = ref<HTMLElement>()

interface SubNode {
  id: string
  name: string
  type: string
  importance: number
}

interface SubEdge {
  source: string
  target: string
  relation: string
  rawRelation: string  // 弱归一原始关系名，优先展示
  pathIndex: number
}

// 悬停 tooltip 状态
const tooltip = reactive({
  visible: false,
  locked: false,
  name: '',
  type: '',
  importance: 0,
  relations: [] as { direction: string, relation: string, target: string }[]
})

// 当前选中的节点 id（点击锁定，再次点击取消）
const selectedNodeId = ref('')

function showTooltip(event: MouseEvent, d: SubNode) {
  tooltip.name = d.name
  tooltip.type = d.type
  tooltip.importance = d.importance
  tooltip.relations = getNodeRelations(d.id)
  tooltip.visible = true
}

function closeTooltip() {
  tooltip.visible = false
  tooltip.locked = false
  selectedNodeId.value = ''
}

function getNodeRelations(nodeId: string): { direction: string, relation: string, target: string }[] {
  const rels: { direction: string, relation: string, target: string }[] = []
  for (const e of currentEdges) {
    const s = typeof e.source === 'string' ? e.source : (e.source as SubNode).id
    const t = typeof e.target === 'string' ? e.target : (e.target as SubNode).id
    // 优先展示原始关系名（如"补贴"），否则展示归一化关系名
    const relLabel = e.rawRelation || e.relation
    if (s === nodeId) {
      rels.push({ direction: '→', relation: relLabel, target: t })
    } else if (t === nodeId) {
      rels.push({ direction: '←', relation: relLabel, target: s })
    }
  }
  return rels
}

function handleTrace() {
  emit('trace', tooltip.name, tooltip.type)
  closeTooltip()
}

// 保存 D3 选中引用
let linkSelection: d3.Selection<SVGLineElement, SubEdge, SVGGElement, unknown> | null = null
let linkLabelSelection: d3.Selection<SVGTextElement, SubEdge, SVGGElement, unknown> | null = null
let nodeSelection: d3.Selection<SVGGElement, SubNode, SVGGElement, unknown> | null = null
let currentNodes: SubNode[] = []
let currentEdges: SubEdge[] = []

function buildGraph(paths: ReasoningPath[], scores?: PerturbationScore[]): { nodes: SubNode[], edges: SubEdge[] } {
  const nodeMap = new Map<string, SubNode>()
  const edges: SubEdge[] = []
  const seen = new Set<string>()

  const importanceMap = new Map<string, number>()
  if (scores) {
    for (const s of scores) {
      importanceMap.set(`${s.node.name}__${s.node.type}`, s.importance)
    }
  }

  for (let pi = 0; pi < paths.length; pi++) {
    const path = paths[pi]
    // 该路径的弱归一原始关系名（仅对 provides 关系有效）
    const providesRawRelation = path.provides_raw_relation || ''
    for (const sp of path.sub_paths) {
      const parseEntity = (raw: string) => {
        const match = raw.match(/^(\w+)\((.+)\)$/)
        if (match) return { type: match[1], name: match[2] }
        return { type: 'Unknown', name: raw }
      }

      const src = parseEntity(sp.subject)
      const tgt = parseEntity(sp.object)

      if (!nodeMap.has(src.name)) {
        const key = `${src.name}__${src.type}`
        nodeMap.set(src.name, { id: src.name, name: src.name, type: src.type, importance: importanceMap.get(key) || 0 })
      }
      if (!nodeMap.has(tgt.name)) {
        const key = `${tgt.name}__${tgt.type}`
        nodeMap.set(tgt.name, { id: tgt.name, name: tgt.name, type: tgt.type, importance: importanceMap.get(key) || 0 })
      }

      const edgeKey = `${src.name}→${sp.relation}→${tgt.name}`
      if (!seen.has(edgeKey)) {
        seen.add(edgeKey)
        // 对于 provides 关系，优先使用 provides_raw_relation
        const rawRelation = (sp.relation === 'provides' && providesRawRelation) ? providesRawRelation : ''
        edges.push({ source: src.name, target: tgt.name, relation: sp.relation, rawRelation, pathIndex: pi })
      }
    }
  }

  return { nodes: Array.from(nodeMap.values()), edges }
}

function applyHighlight(idx: number | undefined) {
  if (!linkSelection || !nodeSelection) return

  if (idx === undefined || idx < 0) {
    linkSelection
      .attr('stroke', '#c4c9d4')
      .attr('stroke-width', 1.5)
      .attr('opacity', 1)
    if (linkLabelSelection) {
      linkLabelSelection.attr('fill', '#6b7280').attr('opacity', 1)
    }
    nodeSelection.attr('opacity', 1)
    return
  }

  const highlightNodeIds = new Set<string>()
  for (const e of currentEdges) {
    if (e.pathIndex === idx) {
      const s = typeof e.source === 'string' ? e.source : (e.source as SubNode).id
      const t = typeof e.target === 'string' ? e.target : (e.target as SubNode).id
      highlightNodeIds.add(s)
      highlightNodeIds.add(t)
    }
  }

  linkSelection
    .attr('stroke', (d: any) => d.pathIndex === idx ? '#3b82f6' : '#e5e7eb')
    .attr('stroke-width', (d: any) => d.pathIndex === idx ? 3 : 1)
    .attr('opacity', (d: any) => d.pathIndex === idx ? 1 : 0.4)

  if (linkLabelSelection) {
    linkLabelSelection
      .attr('fill', (d: any) => d.pathIndex === idx ? '#1f2937' : '#c4c9d4')
      .attr('opacity', (d: any) => d.pathIndex === idx ? 1 : 0.3)
  }

  nodeSelection.attr('opacity', (d: any) => highlightNodeIds.has(d.id) ? 1 : 0.25)
}

function applyNodeHighlight(nodeKey: string | undefined) {
  if (!linkSelection || !nodeSelection) return

  if (!nodeKey) {
    linkSelection.attr('opacity', 1).attr('stroke-width', 1.5)
    if (linkLabelSelection) linkLabelSelection.attr('opacity', 1)
    nodeSelection.attr('opacity', 1)
    return
  }

  const connectedEdgeIndices = new Set<number>()
  for (let i = 0; i < currentEdges.length; i++) {
    const e = currentEdges[i]
    const s = typeof e.source === 'string' ? e.source : (e.source as SubNode).id
    const t = typeof e.target === 'string' ? e.target : (e.target as SubNode).id
    const eKey1 = `${s}__${currentNodes.find(n => n.id === s)?.type || ''}`
    const eKey2 = `${t}__${currentNodes.find(n => n.id === t)?.type || ''}`
    if (eKey1 === nodeKey || eKey2 === nodeKey) {
      connectedEdgeIndices.add(i)
    }
  }

  const connectedNodeIds = new Set<string>()
  for (let i = 0; i < currentEdges.length; i++) {
    if (connectedEdgeIndices.has(i)) {
      const e = currentEdges[i]
      const s = typeof e.source === 'string' ? e.source : (e.source as SubNode).id
      const t = typeof e.target === 'string' ? e.target : (e.target as SubNode).id
      connectedNodeIds.add(s)
      connectedNodeIds.add(t)
    }
  }

  const targetNodeName = nodeKey.split('__')[0]
  connectedNodeIds.add(targetNodeName)

  linkSelection
    .attr('opacity', (_d: any, i: number) => connectedEdgeIndices.has(i) ? 1 : 0.2)
    .attr('stroke-width', (_d: any, i: number) => connectedEdgeIndices.has(i) ? 2.5 : 1)
  if (linkLabelSelection) {
    linkLabelSelection
      .attr('opacity', (_d: any, i: number) => connectedEdgeIndices.has(i) ? 1 : 0.2)
  }

  nodeSelection.attr('opacity', (d: any) => {
    if (d.id === targetNodeName) return 1
    return connectedNodeIds.has(d.id) ? 1 : 0.2
  })
}

function render() {
  if (!containerRef.value) return
  d3.select(containerRef.value).selectAll('svg').remove()

  const { nodes, edges } = buildGraph(props.paths, props.perturbationScores)
  if (nodes.length === 0) return

  currentNodes = nodes
  currentEdges = edges

  const width = containerRef.value.clientWidth
  const nodeCount = nodes.length
  // 根据节点数量动态计算高度，最少 400px，节点越多越高
  const height = Math.max(400, Math.min(700, nodeCount * 50))

  const svg = d3.select(containerRef.value)
    .append('svg')
    .attr('width', width)
    .attr('height', height)

  const g = svg.append('g')

  const zoom = d3.zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.2, 6])
    .on('zoom', (event) => g.attr('transform', event.transform))
  svg.call(zoom)

  const edgesCopy = edges.map(e => ({ ...e }))

  const simulation = d3.forceSimulation(nodes as d3.SimulationNodeDatum[])
    .force('link', d3.forceLink(edgesCopy).id((d: any) => d.id).distance(140))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(36))

  linkSelection = g.append('g')
    .selectAll('line')
    .data(edgesCopy)
    .join('line')
    .attr('stroke', '#c4c9d4')
    .attr('stroke-width', 1.5)

  linkLabelSelection = g.append('g')
    .selectAll('text')
    .data(edgesCopy)
    .join('text')
    .text((d: any) => d.rawRelation || d.relation)
    .attr('font-size', 9)
    .attr('fill', '#6b7280')
    .attr('text-anchor', 'middle')
    .attr('paint-order', 'stroke')
    .attr('stroke', '#ffffff')
    .attr('stroke-width', 3)
    .attr('stroke-opacity', 0.9)

  nodeSelection = g.append('g')
    .selectAll('g')
    .data(nodes)
    .join('g')
    .call(d3.drag<SVGGElement, SubNode>()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart()
        d.fx = d.x; d.fy = d.y
      })
      .on('drag', (event, d) => {
        d.fx = event.x; d.fy = event.y
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0)
        d.fx = null; d.fy = null
      })
    )

  function getRadius(d: SubNode): number {
    const cnt = edgesCopy.filter((e: any) => {
      const s = typeof e.source === 'string' ? e.source : (e.source as SubNode).id
      const t = typeof e.target === 'string' ? e.target : (e.target as SubNode).id
      return s === d.id || t === d.id
    }).length
    return Math.max(16, Math.min(28, 14 + cnt * 3))
  }

  /**
   * 生成从底部向上填充的圆缺（circular segment）路径
   * 效果等同 clipPath + rect，但不依赖 clip-path 避免矩形 bug
   */
  function buildFillPath(cx: number, cy: number, r: number, pct: number): string | null {
    if (pct <= 0) return null
    if (pct >= 1) {
      return `M${cx},${cy - r}A${r},${r} 0 1,1 ${cx - 0.01},${cy - r}Z`
    }
    // 填充顶部 y 坐标（从底部 r 向上）
    const fillY = r - 2 * r * pct
    const chordHalf = Math.max(0, Math.sqrt(r * r - fillY * fillY))
    const largeArc = fillY < 0 ? 1 : 0
    return `M${cx - chordHalf},${cy + fillY}L${cx + chordHalf},${cy + fillY}A${r},${r} 0 ${largeArc},1 ${cx - chordHalf},${cy + fillY}Z`
  }

  // 底层圆
  nodeSelection!.append('circle')
    .attr('r', (d) => getRadius(d))
    .attr('fill', (d) => getNodeColor(d.type) + '30')
    .attr('stroke', (d) => getNodeColor(d.type))
    .attr('stroke-width', 2)
    .style('cursor', 'pointer')

  // 填充圆缺（从底部向上填充，不用 clipPath 避免矩形 bug）
  nodeSelection!.each(function(d) {
    const r = getRadius(d)
    const imp = Math.min(1, Math.max(0, d.importance))
    if (imp <= 0) return

    const cx = 0, cy = 0
    const pathD = buildFillPath(cx, cy, r, imp)
    if (pathD) {
      d3.select(this).append('path')
        .attr('d', pathD)
        .attr('fill', getNodeColor(d.type))
        .attr('opacity', 0.85)
    }
  })

  // 百分比文字
  nodeSelection!.filter((d) => d.importance > 0)
    .append('text')
    .text((d) => `${Math.round(Math.min(1, Math.max(0, d.importance)) * 100)}%`)
    .attr('text-anchor', 'middle')
    .attr('dy', 4)         // 居中显示，不偏移
    .attr('font-size', (d) => getRadius(d) >= 22 ? 11 : 9)
    .attr('font-weight', 700)
    .attr('fill', '#ffffff')
    .style('pointer-events', 'none')

  // 节点名称标签
  nodeSelection!.append('text')
    .text((d) => d.name.length > 10 ? d.name.substring(0, 10) + '...' : d.name)
    .attr('dx', (d) => getRadius(d) + 6)
    .attr('dy', 4)
    .attr('font-size', 11)
    .attr('font-weight', 500)
    .attr('fill', '#1f2937')
    .attr('paint-order', 'stroke')
    .attr('stroke', '#ffffff')
    .attr('stroke-width', 3)
    .attr('stroke-opacity', 0.9)

  // 悬停：只高亮边框，不改变 tooltip（锁定状态下完全不干扰信息卡）
  nodeSelection!.on('mouseenter', function(event: MouseEvent, d: SubNode) {
    d3.select(this).selectAll('circle').attr('stroke-width', 4)
    // 未锁定时悬停可显示 tooltip
    if (!tooltip.locked) {
      showTooltip(event, d)
    }
  }).on('mouseleave', function() {
    d3.select(this).selectAll('circle').filter(function(_, i) { return i === 0 }).attr('stroke-width', 2)
    // locked 时不关闭
    if (!tooltip.locked) {
      tooltip.visible = false
    }
  })

  // 点击节点 → 锁定/取消弹窗
  nodeSelection!.on('click', (event, d) => {
    event.stopPropagation()
    event.stopImmediatePropagation()
    if (selectedNodeId.value === d.id) {
      // 再次点击同一个节点 → 解除锁定
      selectedNodeId.value = ''
      tooltip.locked = false
      tooltip.visible = false
    } else {
      // 锁定并显示当前节点
      selectedNodeId.value = d.id
      tooltip.locked = true
      tooltip.visible = true
      // 直接填充 tooltip 数据
      tooltip.name = d.name
      tooltip.type = d.type
      tooltip.importance = d.importance
      tooltip.relations = getNodeRelations(d.id)
    }
  })

  // 点击空白关闭 tooltip
  svg.on('click', () => {
    selectedNodeId.value = ''
    tooltip.locked = false
    tooltip.visible = false
  })

  // 仿真 tick
  simulation.on('tick', () => {
    linkSelection!
      .attr('x1', (d: any) => d.source.x)
      .attr('y1', (d: any) => d.source.y)
      .attr('x2', (d: any) => d.target.x)
      .attr('y2', (d: any) => d.target.y)

    linkLabelSelection!
      .attr('x', (d: any) => (d.source.x + d.target.x) / 2)
      .attr('y', (d: any) => (d.source.y + d.target.y) / 2 - 4)

    nodeSelection!.attr('transform', (d: any) => `translate(${d.x},${d.y})`)
  })

  applyHighlight(props.highlightPathIndex)
}

onMounted(() => render())

watch(() => [props.paths, props.perturbationScores], () => render(), { deep: true })

watch(() => props.highlightPathIndex, (idx) => {
  if (props.highlightNodeKey) return
  applyHighlight(idx)
})

watch(() => props.highlightNodeKey, (key) => {
  if (key) {
    applyNodeHighlight(key)
  } else {
    applyNodeHighlight(undefined)
    applyHighlight(props.highlightPathIndex)
  }
})
</script>

<style scoped lang="scss">
.subgraph-container {
  width: 100%;
  background: #fafbfc;
  border-radius: 8px;
  overflow: visible;
  border: 1px solid #e5e7eb;
  position: relative;
  min-height: 400px;
}

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

  .tooltip-importance {
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
    .tooltip-bar-track {
      flex: 1;
      height: 6px;
      background: #f3f4f6;
      border-radius: 3px;
      overflow: hidden;
      .tooltip-bar-fill {
        height: 100%;
        border-radius: 3px;
        transition: width 0.2s;
      }
    }
    .tooltip-value {
      font-size: 12px;
      font-weight: 600;
      color: #374151;
      min-width: 40px;
      text-align: right;
    }
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
      .rel-target { color: #3b82f6; font-weight: 500; }
    }
    .tooltip-more {
      font-size: 11px;
      color: #9ca3af;
      margin-top: 2px;
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
</style>
