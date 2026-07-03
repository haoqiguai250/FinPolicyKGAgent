<template>
  <div class="sidebar">
    <!-- Logo / 品牌 -->
    <div class="sidebar-header">
      <div class="sidebar-brand">
        <img src="/src/assets/logo.jpg" class="sidebar-avatar" alt="FinPolicyKG" />
        <div class="brand-text">
          <span class="brand-name">FinPolicy</span>
          <span class="brand-sub">AI 政策顾问</span>
        </div>
      </div>
    </div>

    <!-- 导航菜单 -->
    <nav class="sidebar-nav">
      <router-link
        v-for="item in navItems"
        :key="item.path + item.label"
        :to="item.path"
        class="nav-item"
        :class="{ active: isActive(item) }"
      >
        <el-icon :size="20"><component :is="item.icon" /></el-icon>
        <span class="nav-label">{{ item.label }}</span>
        <span v-if="item.badge" class="nav-badge">{{ item.badge }}</span>
      </router-link>
    </nav>

    <!-- 分隔线 -->
    <div class="sidebar-divider" />

    <!-- 设置 -->
    <div class="sidebar-bottom">
      <router-link to="/settings" class="nav-item" :class="{ active: $route.path === '/settings' }">
        <el-icon :size="20"><Setting /></el-icon>
        <span class="nav-label">设置</span>
      </router-link>
    </div>

    <!-- IP 角色区 -->
    <div class="sidebar-character">
      <div class="character-bubble">
        <span class="bubble-icon">🤖</span>
        <div class="bubble-text">
          <span class="bubble-title">AI 助手在线</span>
          <span class="bubble-sub">随时为您服务</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import { Suitcase, ChatDotSquare, OfficeBuilding, Clock, DataAnalysis, Share, Setting, Calendar } from '@element-plus/icons-vue'

const route = useRoute()

interface NavItem {
  path: string
  label: string
  icon: any
  badge?: string
  beta?: boolean
}

const navItems: NavItem[] = [
  { path: '/workspace', label: '工作台', icon: Suitcase },
  { path: '/advisor', label: '查询', icon: ChatDotSquare },
  { path: '/kg-explorer', label: '知识图谱', icon: Share, badge: 'Beta' },
  { path: '/profile', label: '我的企业', icon: OfficeBuilding },
  { path: '/push-records', label: '历史申报', icon: Clock },
  { path: '/calendar', label: '申报日历', icon: Calendar },
  { path: '/dashboard', label: '数据报表', icon: DataAnalysis },
]

function isActive(item: NavItem): boolean {
  // 精准匹配当前路由
  return route.path === item.path || route.path.startsWith(item.path + '/')
}
</script>

<style scoped lang="scss">
.sidebar {
  width: var(--sidebar-width);
  background: var(--color-sidebar-bg);
  display: flex;
  flex-direction: column;
  padding: 20px 16px 16px;
  flex-shrink: 0;
  height: 100vh;
  box-sizing: border-box;
  border-right: 1px solid var(--color-border-light);
}

.sidebar-header {
  margin-bottom: 24px;
  padding: 0 4px;

  .sidebar-brand {
    display: flex;
    align-items: center;
    gap: 12px;

    .sidebar-avatar {
      width: 40px;
      height: 40px;
      border-radius: var(--radius-sm);
      object-fit: cover;
      flex-shrink: 0;
    }

    .brand-text {
      display: flex;
      flex-direction: column;
      gap: 1px;
      min-width: 0;

      .brand-name {
        font-size: 16px;
        font-weight: 700;
        color: var(--color-text);
        letter-spacing: -0.01em;
      }

      .brand-sub {
        font-size: 11px;
        color: var(--color-text-placeholder);
      }
    }
  }
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  overflow-y: auto;
}

.sidebar-divider {
  height: 1px;
  background: var(--color-border-light);
  margin: 8px 4px 12px;
}

.sidebar-bottom {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  text-decoration: none;
  transition: all 0.15s ease;
  position: relative;

  :deep(.el-icon) {
    color: var(--color-icon-default);
    flex-shrink: 0;
  }

  .nav-label {
    font-size: 14px;
    font-weight: 500;
    color: var(--color-text-secondary);
    white-space: nowrap;
  }

  .nav-badge {
    margin-left: auto;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: var(--radius-pill);
    background: var(--color-primary-bg);
    color: var(--color-primary);
    letter-spacing: 0.02em;
  }

  &:hover {
    background: rgba(91, 77, 255, 0.04);

    :deep(.el-icon) { color: var(--color-primary); }
    .nav-label { color: var(--color-primary); }
  }

  &.active {
    background: var(--color-primary-bg);

    :deep(.el-icon) { color: var(--color-primary); }
    .nav-label { color: var(--color-primary); font-weight: 600; }
  }
}

.sidebar-character {
  margin-top: auto;
  padding-top: 12px;

  .character-bubble {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px;
    border-radius: var(--radius-md);
    background: linear-gradient(135deg, rgba(91, 77, 255, 0.06), rgba(125, 107, 255, 0.03));
    border: 1px solid rgba(91, 77, 255, 0.08);

    .bubble-icon {
      font-size: 28px;
      line-height: 1;
    }

    .bubble-text {
      display: flex;
      flex-direction: column;
      gap: 1px;
      min-width: 0;

      .bubble-title {
        font-size: 13px;
        font-weight: 600;
        color: var(--color-text);
      }

      .bubble-sub {
        font-size: 11px;
        color: var(--color-text-placeholder);
      }
    }
  }
}
</style>
