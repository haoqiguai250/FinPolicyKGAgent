<template>
  <div class="page-header">
    <div class="page-header-left">
      <h1 class="page-header-title">{{ title }}</h1>
      <p v-if="description" class="page-header-desc">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="page-header-actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<style scoped lang="scss">
.page-header {
  @include page-header;
}

.page-header-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
  line-height: 1.3;
}

.page-header-desc {
  color: var(--color-text-secondary);
  font-size: 14px;
  margin-top: 6px;
}

.page-header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
