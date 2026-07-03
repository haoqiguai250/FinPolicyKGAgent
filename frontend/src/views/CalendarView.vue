<template>
  <div class="calendar-page">
    <div class="page-header">
      <div class="page-title">
        <h1>申报日历</h1>
        <p class="page-desc">查看截止日期排期、管理申报优先级</p>
      </div>
      <div class="page-controls">
        <el-select v-model="selectedEnterpriseId" placeholder="选择企业" style="width: 200px;" @change="loadCalendar">
          <el-option v-for="ent in enterprises" :key="ent.enterprise_id" :label="ent.name" :value="ent.enterprise_id" />
        </el-select>
        <el-button @click="prevMonth">&lt;</el-button>
        <span class="month-label">{{ currentMonth }}</span>
        <el-button @click="nextMonth">&gt;</el-button>
      </div>
    </div>

    <!-- 推荐排期 -->
    <div v-if="schedule.length > 0" class="schedule-section card">
      <h3>推荐申报顺序</h3>
      <div class="schedule-list">
        <div
          v-for="item in schedule"
          :key="item.opportunity_id"
          class="schedule-item"
          :class="{ eligible: item.is_eligible }"
        >
          <span class="rank">{{ item.recommendation_rank }}</span>
          <span class="name">{{ item.policy_name }}</span>
          <el-tag size="small" :type="item.is_eligible ? 'success' : 'danger'" effect="plain">
            {{ item.is_eligible ? '可申报' : '不符合' }}
          </el-tag>
          <span v-if="item.deadline" class="deadline-info">
            {{ item.days_until_deadline }}天后截止
          </span>
          <span class="reason">{{ item.recommendation_reason }}</span>
        </div>
      </div>
    </div>

    <!-- 日历网格 -->
    <div v-if="calendarDays.length > 0" class="calendar-section">
      <div
        v-for="day in calendarDays"
        :key="day.date"
        class="calendar-day card"
        :class="dayClass(day)"
      >
        <div class="day-header">
          <span class="day-date">{{ formatDate(day.date) }}</span>
          <span class="day-count">{{ day.opportunities.length }} 条</span>
        </div>
        <div class="day-opps">
          <div
            v-for="evt in day.opportunities"
            :key="evt.opportunity_id"
            class="day-opp"
            :class="'urgency-' + evt.urgency"
          >
            <span class="opp-name">{{ evt.policy_name }}</span>
            <el-tag size="small" :type="urgencyTagType(evt.urgency)" effect="plain">
              {{ evt.urgency === 'overdue' ? '已过期' : evt.days_left + '天' }}
            </el-tag>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="!loading && selectedEnterpriseId" class="empty-state card">
      <div class="empty-icon">📅</div>
      <h3>当月无截止政策</h3>
      <p>选择其他月份或企业查看</p>
    </div>

    <div v-else-if="!selectedEnterpriseId" class="empty-state card">
      <div class="empty-icon">📋</div>
      <h3>请先选择企业</h3>
      <p>选择企业后查看申报日历</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { CalendarDay, ScheduleItem, Enterprise } from '../types/advisor'
import { fetchCalendar, fetchSchedule, fetchEnterprises } from '../api/advisor'

const enterprises = ref<Enterprise[]>([])
const selectedEnterpriseId = ref('')
const currentYear = ref(new Date().getFullYear())
const currentMonthNum = ref(new Date().getMonth() + 1)
const calendarDays = ref<CalendarDay[]>([])
const schedule = ref<ScheduleItem[]>([])
const loading = ref(false)

const currentMonth = computed(() => `${currentYear.value}-${String(currentMonthNum.value).padStart(2, '0')}`)

onMounted(async () => {
  try {
    const result = await fetchEnterprises()
    enterprises.value = result.enterprises || []
  } catch (e) {
    console.error('加载企业列表失败:', e)
  }
})

async function loadCalendar() {
  if (!selectedEnterpriseId.value) return
  loading.value = true
  try {
    const [calResult, schedResult] = await Promise.all([
      fetchCalendar(selectedEnterpriseId.value, currentMonth.value),
      fetchSchedule(selectedEnterpriseId.value),
    ])
    calendarDays.value = calResult.calendar || []
    schedule.value = (schedResult.schedule || []) as ScheduleItem[]
  } catch (e) {
    console.error('加载日历失败:', e)
  } finally {
    loading.value = false
  }
}

function prevMonth() {
  if (currentMonthNum.value === 1) {
    currentMonthNum.value = 12
    currentYear.value--
  } else {
    currentMonthNum.value--
  }
  loadCalendar()
}

function nextMonth() {
  if (currentMonthNum.value === 12) {
    currentMonthNum.value = 1
    currentYear.value++
  } else {
    currentMonthNum.value++
  }
  loadCalendar()
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

function dayClass(day: CalendarDay): string {
  const hasHigh = day.opportunities.some(o => o.urgency === 'high' || o.urgency === 'overdue')
  return hasHigh ? 'day-urgent' : ''
}

function urgencyTagType(urgency: string): string {
  const types: Record<string, string> = {
    overdue: 'danger',
    high: 'danger',
    medium: 'warning',
    low: 'info',
  }
  return types[urgency] || 'info'
}
</script>

<style scoped lang="scss">
.calendar-page {
  max-width: 960px;
  margin: 0 auto;
  padding: var(--spacing-lg);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-lg);
  flex-wrap: wrap;
  gap: 12px;

  .page-title h1 {
    font-size: 22px;
    font-weight: 700;
    color: var(--color-text-primary);
    margin: 0;
  }
  .page-desc {
    color: var(--color-text-secondary);
    font-size: 14px;
    margin-top: 6px;
  }
  .page-controls {
    display: flex;
    gap: 8px;
    align-items: center;
  }
  .month-label {
    font-size: 16px;
    font-weight: 600;
    min-width: 80px;
    text-align: center;
  }
}

.card {
  background: var(--color-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
  box-shadow: var(--shadow-sm);
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  .empty-icon { font-size: 48px; margin-bottom: 12px; }
  h3 { font-size: 16px; color: var(--color-text-primary); margin: 0 0 6px; }
  p { color: var(--color-text-secondary); font-size: 14px; margin: 0; }
}

.schedule-section {
  margin-bottom: 16px;
  h3 { font-size: 15px; font-weight: 600; margin: 0 0 12px; }
}

.schedule-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.schedule-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 8px;
  background: #f9fafb;
  font-size: 13px;

  &.eligible { border-left: 3px solid #059669; }

  .rank {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: #e5e7eb;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    font-size: 12px;
  }
  .eligible .rank { background: #d1fae5; }

  .name { font-weight: 500; flex: 1; }
  .deadline-info { color: #d97706; font-size: 12px; }
  .reason { color: var(--color-text-secondary); font-size: 12px; }
}

.calendar-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.calendar-day {
  padding: 12px 16px;

  &.day-urgent { border-left: 3px solid #ef4444; }
}

.day-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  .day-date { font-weight: 600; font-size: 14px; }
  .day-count { font-size: 12px; color: var(--color-text-secondary); }
}

.day-opps {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.day-opp {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 13px;

  &.urgency-high, &.urgency-overdue { background: #fef2f2; }
  &.urgency-medium { background: #fffbeb; }
  &.urgency-low { background: #f0fdf4; }

  .opp-name { flex: 1; font-weight: 500; }
}
</style>
