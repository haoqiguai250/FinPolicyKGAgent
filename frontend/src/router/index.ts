import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/workspace',
    },
    {
      path: '/dashboard',
      name: 'Dashboard',
      component: () => import('../views/Dashboard.vue'),
      meta: { title: '仪表盘', icon: 'Odometer' },
    },
    {
      path: '/workspace',
      name: 'ApplicationWorkspace',
      component: () => import('../views/ApplicationWorkspace.vue'),
      meta: { title: '申报工作台', icon: 'Suitcase' },
    },
    {
      path: '/advisor',
      name: 'Advisor',
      component: () => import('../views/Advisor.vue'),
      meta: { title: '决策查询', icon: 'Search' },
    },
    {
      path: '/kg-explorer',
      name: 'KGExplorer',
      component: () => import('../views/KGExplorer.vue'),
      meta: { title: '知识图谱', icon: 'Share' },
    },
    {
      path: '/evaluation',
      name: 'Evaluation',
      component: () => import('../views/Evaluation.vue'),
      meta: { title: '评估报告', icon: 'DataAnalysis' },
    },
    {
      path: '/profile',
      name: 'Profile',
      component: () => import('../views/ProfileConfig.vue'),
      meta: { title: '画像配置', icon: 'UserFilled' },
    },
    {
      path: '/push-records',
      name: 'PushRecords',
      component: () => import('../views/PushRecords.vue'),
      meta: { title: '推送记录', icon: 'Bell' },
    },
    {
      path: '/calendar',
      name: 'Calendar',
      component: () => import('../views/CalendarView.vue'),
      meta: { title: '申报日历', icon: 'Calendar' },
    },
  ],
})

export default router
