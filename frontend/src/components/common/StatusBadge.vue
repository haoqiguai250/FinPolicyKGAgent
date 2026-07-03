<template>
  <span class="status-badge" :class="'status-' + status">
    <span class="status-dot" />
    <span class="status-text">{{ label }}</span>
  </span>
</template>

<script setup lang="ts">
const props = defineProps<{
  status: string
  label?: string
}>()

const defaultLabels: Record<string, string> = {
  discovered: '已发现',
  applying: '申报中',
  submitted: '已提交',
  approved: '已通过',
  rejected: '未通过',
  preparing: '准备中',
  ready: '已就绪',
  waived: '豁免',
  generating: '生成中',
  generated: '已生成',
  error: '错误',
}

const label = props.label || defaultLabels[props.status] || props.status
</script>

<style scoped lang="scss">
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.2s ease;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-text {
  line-height: 1;
}

// 状态配色
.status-discovered {
  background: #f3f4f6;
  color: #6b7280;
  .status-dot { background: #9ca3af; }
}

.status-applying {
  background: #fffbeb;
  color: #92400e;
  .status-dot { background: #f59e0b; }
}

.status-submitted {
  background: #eff6ff;
  color: #1e40af;
  .status-dot { background: #3b82f6; }
}

.status-approved {
  background: #f0fdf4;
  color: #166534;
  .status-dot { background: #22c55e; }
}

.status-rejected {
  background: #fef2f2;
  color: #991b1b;
  .status-dot { background: #ef4444; }
}

.status-preparing {
  background: #f9fafb;
  color: #4b5563;
  .status-dot { background: #9ca3af; }
}

.status-ready {
  background: #f0fdf4;
  color: #166534;
  .status-dot { background: #22c55e; }
}

.status-waived {
  background: #fffbeb;
  color: #92400e;
  .status-dot { background: #f59e0b; }
}

.status-generating {
  background: #eff6ff;
  color: #1e40af;
  .status-dot { background: #3b82f6; animation: pulse 1.5s infinite; }
}

.status-generated {
  background: #f0fdf4;
  color: #166534;
  .status-dot { background: #22c55e; }
}

.status-error {
  background: #fef2f2;
  color: #991b1b;
  .status-dot { background: #ef4444; }
}
</style>
