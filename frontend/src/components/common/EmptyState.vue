<template>
  <div class="empty-state">
    <div class="empty-icon">
      <el-icon :size="48" :color="iconColor">
        <component :is="icon" />
      </el-icon>
    </div>
    <h3 class="empty-title">{{ title }}</h3>
    <p v-if="description" class="empty-desc">{{ description }}</p>
    <slot />
  </div>
</template>

<script setup lang="ts">
import { Component } from 'vue'

defineProps<{
  icon: Component
  title: string
  description?: string
  iconColor?: string
}>()
</script>

<style scoped lang="scss">
.empty-state {
  @include flex-col-center;
  padding: 60px 20px;
  text-align: center;
}

.empty-icon {
  margin-bottom: 16px;
  opacity: 0.6;
}

.empty-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 6px;
}

.empty-desc {
  color: var(--color-text-secondary);
  font-size: 14px;
  margin: 0 0 16px;
}
</style>
