<template>
  <div class="app-layout">
    <Sidebar />
    <div class="main-area">
      <div class="page-content">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Sidebar from './components/layout/Sidebar.vue'
</script>

<style lang="scss">
@use './styles/variables.scss';
@use './styles/global.scss';

.app-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--color-bg);
}

.page-content {
  flex: 1;
  overflow-y: auto;
  background: var(--color-bg);
}
</style>
