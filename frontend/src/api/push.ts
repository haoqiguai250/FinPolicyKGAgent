import type { EnterpriseProfile, PushRecord, PushPreference, DeadlineRemindersResponse } from '../types/push'
import { mockFetchProfile, mockSaveProfile, mockFetchPushRecords } from './mock/push.mock'

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

/**
 * 获取当前企业画像
 */
export async function fetchProfile(): Promise<EnterpriseProfile> {
  if (USE_MOCK) {
    return mockFetchProfile()
  }
  const { default: client } = await import('./client')
  return client.get('/push/profile')
}

/**
 * 保存企业画像
 */
export async function saveProfile(profile: EnterpriseProfile): Promise<{ status: string; message: string }> {
  if (USE_MOCK) {
    return mockSaveProfile(profile)
  }
  const { default: client } = await import('./client')
  return client.put('/push/profile', profile)
}

/**
 * 获取推送偏好
 */
export async function fetchPushPreferences(): Promise<PushPreference> {
  if (USE_MOCK) {
    return {
      enabled: true,
      deadline_remind_days: 30,
      remind_missing_fields: true,
      regions: [],
    }
  }
  const { default: client } = await import('./client')
  return client.get('/push/preferences')
}

/**
 * 保存推送偏好
 */
export async function savePushPreferences(pref: PushPreference): Promise<{ status: string; message: string }> {
  if (USE_MOCK) {
    return { status: 'ok', message: '推送偏好已保存' }
  }
  const { default: client } = await import('./client')
  return client.put('/push/preferences', pref)
}

/**
 * 获取截止日期提醒
 */
export async function fetchDeadlineReminders(daysAhead: number = 30): Promise<DeadlineRemindersResponse> {
  if (USE_MOCK) {
    return { total: 0, reminders: [] }
  }
  const { default: client } = await import('./client')
  return client.get('/push/deadlines', { params: { days_ahead: daysAhead } })
}

/**
 * 获取推送记录列表
 * @param date 可选，日期 YYYYMMDD
 */
export async function fetchPushRecords(date?: string): Promise<{ total: number; records: PushRecord[] }> {
  if (USE_MOCK) {
    return mockFetchPushRecords(date)
  }
  const { default: client } = await import('./client')
  const params = date ? { date } : undefined
  return client.get('/push/records', { params })
}
